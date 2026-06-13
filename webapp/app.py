"""Job-application web UI.

Run with `python -m jobsearch ui` → http://127.0.0.1:8484. Local-only by
design: the database holds profile PII and application history.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobsearch.resume import extract_keywords, pdf_to_text

from . import db, emailmod, gmail, ingest, profile
from .apply_browser import SessionRegistry
from .runner import PipelineRunner
from .textfmt import description_html

HERE = Path(__file__).parent


def create_app(root: Path, db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="jobsearch UI")
    db_path = db_path or root / "data" / "jobsearch.db"
    conn = db.connect(db_path)
    profile.ensure_seeded(conn, root)
    sessions = SessionRegistry(db_path, root / "data" / "browser_profile",
                               data_dir=root / "data")
    runner = PipelineRunner(root)
    app.state.runner = runner

    # Guards against launching overlapping background pipeline runs.
    _pipeline_state = {"running": False}

    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["qp"] = quote_plus
    templates.env.filters["description_html"] = description_html
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def render(request: Request, template: str, **ctx) -> HTMLResponse:
        ctx.setdefault("counts", db.stack_counts(conn))
        return templates.TemplateResponse(request, template, ctx)

    # ------------------------------------------------------------ dashboard
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, q: str = "", company: str = "", stack: str = "",
                  near_miss: str = "1", sort_by: str = "", sort_dir: str = "",
                  min_fit: str = "", status_filter: str = ""):
        min_fit_val = float(min_fit) if min_fit else None
        jobs = db.search_jobs(conn, q=q, company=company, stack=stack,
                              include_near_miss=near_miss == "1",
                              sort_by=sort_by, sort_dir=sort_dir,
                              min_fit=min_fit_val, status_filter=status_filter)
        companies = [r["company"] for r in conn.execute(
            "SELECT DISTINCT company FROM jobs ORDER BY company").fetchall()]
        last_run = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return render(request, "dashboard.html", jobs=jobs, q=q, company=company,
                      stack=stack, near_miss=near_miss, companies=companies,
                      last_run=last_run, sort_by=sort_by, sort_dir=sort_dir,
                      min_fit=min_fit, status_filter=status_filter,
                      all_statuses=db.APP_STATUSES)

    # ------------------------------------------------------------ job detail
    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        job = db.job_with_application(conn, job_id)
        if job is None:
            return RedirectResponse("/", status_code=303)
        events = conn.execute(
            """SELECT 'job' AS kind, event_type AS label, payload AS detail, created_at
               FROM job_events WHERE job_id = ?
               UNION ALL
               SELECT 'application', status, detail, created_at
               FROM application_events WHERE application_id = ?
               ORDER BY created_at DESC""",
            (job_id, job["application_id"])).fetchall()
        emails = conn.execute(
            "SELECT * FROM email_messages WHERE job_id = ? ORDER BY sent_at DESC",
            (job_id,)).fetchall()
        return render(request, "job_detail.html", job=job, events=events,
                      emails=emails, statuses=db.APP_STATUSES,
                      profile_fields=profile.all_fields(conn))

    # --------------------------------------------------------------- actions
    @app.post("/jobs/{job_id}/apply")
    def apply(job_id: int):
        job = db.job_with_application(conn, job_id)
        if job is None or not job["url"]:
            return JSONResponse({"error": "job or url missing"}, status_code=404)
        session = sessions.launch(job["application_id"], job["url"])
        return JSONResponse({"state": session.state})

    @app.get("/api/apply-status/{application_id}")
    def apply_status(application_id: int):
        status = sessions.status(application_id)  # includes the fill summary
        row = conn.execute("SELECT status FROM applications WHERE id = ?",
                           (application_id,)).fetchone()
        status["application_status"] = row["status"] if row else "unknown"
        return JSONResponse(status)

    @app.post("/applications/{application_id}/status")
    def set_status(application_id: int, status: str = Form(...), note: str = Form("")):
        if status in db.APP_STATUSES:
            db.set_application_status(conn, application_id, status,
                                      detail=note or "set manually", via="ui")
        if note:
            conn.execute("UPDATE applications SET notes = ? WHERE id = ?",
                         (note, application_id))
            conn.commit()
        job = conn.execute("SELECT job_id FROM applications WHERE id = ?",
                           (application_id,)).fetchone()
        return RedirectResponse(f"/jobs/{job['job_id']}" if job else "/", status_code=303)

    @app.post("/run")
    def start_pipeline():
        started = runner.start()
        return JSONResponse({"started": started},
                            status_code=200 if started else 409)

    @app.get("/run/log")
    def pipeline_log(since: int = 0):
        # Seamless finish: first poll after a successful run ingests the
        # fresh report so the dashboard fills without a separate click.
        if runner.exit_code == 0 and not runner.running and not runner.ingested:
            runner.ingested = True
            try:
                counts = ingest.ingest_latest(root, conn)
                runner.lines.append(
                    f"Ingested into UI: {counts['inserted']} new, "
                    f"{counts['updated']} updated jobs. Refresh the dashboard.")
            except Exception as exc:  # noqa: BLE001 — surface in the log panel
                runner.lines.append(f"Ingest failed: {exc}")
        return JSONResponse(runner.snapshot(since))

    @app.post("/ingest")
    def do_ingest():
        try:
            counts = ingest.ingest_latest(root, conn)
        except FileNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return RedirectResponse(f"/?ingested={counts['inserted']}", status_code=303)

    # ------------------------------------------------------- resume & profile
    def _role_profile(resume_text: str):
        """The occupation(s)/skills the current resume targets — what the next
        run will search for. Best-effort: never let a matcher hiccup 500 the
        resume page."""
        if not resume_text:
            return None
        try:
            from jobsearch.config import load_settings
            from jobsearch.role_profile import resolve_profile
            settings = load_settings(root / "config" / "settings.yaml")
            return resolve_profile(root, settings, resume_text)
        except Exception:  # noqa: BLE001
            return None

    @app.get("/resume", response_class=HTMLResponse)
    def resume(request: Request, uploaded: int = 0, error: str = "", started: int = 0):
        text_path = root / "data" / "resume.txt"
        using_sample = not text_path.exists()
        if using_sample:
            text_path = root / "data" / "sample_resume.txt"
        resume_text = text_path.read_text() if text_path.exists() else ""
        pdfs = sorted((root / "data").glob("*.pdf"))
        # Sections split on blank lines for per-block copy buttons.
        sections = [s.strip() for s in resume_text.split("\n\n") if s.strip()]
        return render(request, "resume.html", resume_text=resume_text,
                      sections=sections, pdf_name=pdfs[-1].name if pdfs else "",
                      using_sample=using_sample, uploaded=uploaded, error=error,
                      started=started, role_profile=_role_profile(resume_text),
                      pipeline_running=_pipeline_state["running"],
                      keywords=extract_keywords(resume_text) if resume_text else [])

    @app.post("/resume/upload")
    async def upload_resume(file: UploadFile = File(...)):
        data = await file.read()
        name = (file.filename or "").lower()
        try:
            if name.endswith(".pdf"):
                text = pdf_to_text(data)
                (root / "data" / "resume.pdf").write_bytes(data)
            elif name.endswith((".txt", ".md")):
                text = data.decode("utf-8", errors="replace").strip()
                if len(text) < 100:
                    raise ValueError("that file looks too short to be a resume")
            else:
                raise ValueError("upload a .pdf or .txt resume")
        except ValueError as exc:
            return RedirectResponse(f"/resume?error={quote_plus(str(exc))}",
                                    status_code=303)
        (root / "data" / "resume.txt").write_text(text + "\n")
        profile.reseed_from_resume(conn, text)
        return RedirectResponse("/resume?uploaded=1", status_code=303)

    @app.post("/resume/run")
    def run_pipeline():
        """Kick off a full pipeline run (discover → fetch → rank) in the
        background, targeting the role profile derived from the current resume.
        Returns immediately; progress shows in the server log, results land in
        the dashboard after the next 'Ingest latest run'."""
        import threading

        from jobsearch import pipeline

        if _pipeline_state["running"]:
            return RedirectResponse("/resume?started=2", status_code=303)

        def _go():
            try:
                pipeline.run(root)
            except Exception as exc:  # noqa: BLE001 — surfaced via the log
                print(f"pipeline run failed: {exc}")
            finally:
                _pipeline_state["running"] = False

        _pipeline_state["running"] = True
        threading.Thread(target=_go, daemon=True).start()
        return RedirectResponse("/resume?started=1", status_code=303)

    @app.get("/resume.pdf")
    def resume_pdf():
        pdfs = sorted((root / "data").glob("*.pdf"))
        if not pdfs:
            return JSONResponse({"error": "no PDF in data/"}, status_code=404)
        return FileResponse(pdfs[-1], media_type="application/pdf")

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request):
        return render(request, "profile.html", fields=profile.all_fields(conn))

    @app.post("/profile")
    async def save_profile(request: Request):
        form = await request.form()
        for field, value in form.items():
            profile.set_field(conn, field, str(value))
        return RedirectResponse("/profile", status_code=303)

    # ------------------------------------------------------ search config view
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        settings = yaml.safe_load((root / "config" / "settings.yaml").read_text())
        companies_cfg = yaml.safe_load((root / "config" / "companies.yaml").read_text())
        return render(request, "settings.html", search=settings.get("search", {}),
                      ranking=settings.get("ranking", {}),
                      companies=companies_cfg.get("companies", []),
                      manual=companies_cfg.get("manual_check", []))

    # ----------------------------------------------------------- email module
    @app.get("/emails", response_class=HTMLResponse)
    def emails_page(request: Request, q: str = "", error: str = "",
                    connected_as: str = "", synced: str = ""):
        connected = emailmod.is_connected(conn)
        account = conn.execute(
            "SELECT address FROM email_accounts WHERE status = 'connected' LIMIT 1").fetchone()
        sql = """SELECT m.*, j.company AS job_company, j.title AS job_title
                 FROM email_messages m LEFT JOIN jobs j ON j.id = m.job_id"""
        args: list = []
        if q:
            sql += " WHERE m.subject LIKE ? OR m.from_addr LIKE ? OR m.body LIKE ?"
            args = [f"%{q}%"] * 3
        sql += " ORDER BY m.sent_at DESC LIMIT 200"
        messages = conn.execute(sql, args).fetchall()
        return render(request, "emails.html", connected=connected, messages=messages,
                      q=q, setup=emailmod.SETUP_INSTRUCTIONS, error=error,
                      address=account["address"] if account else "", synced=synced,
                      has_credentials=gmail.load_client(root / "data") is not None)

    def _redirect_uri(request: Request) -> str:
        return str(request.base_url).rstrip("/") + "/emails/oauth/callback"

    @app.post("/emails/connect")
    def emails_connect(request: Request):
        client = gmail.load_client(root / "data")
        if client is None:
            return RedirectResponse(
                "/emails?error=No+data%2Fcredentials.json+—+follow+the+setup+steps",
                status_code=303)
        state = gmail.new_state()
        app.state.oauth_states.add(state)
        return RedirectResponse(
            gmail.build_auth_url(client, _redirect_uri(request), state), status_code=303)

    @app.get("/emails/oauth/callback")
    def emails_oauth_callback(request: Request, code: str = "", state: str = "",
                              error: str = ""):
        if error or not code or state not in app.state.oauth_states:
            return RedirectResponse("/emails?error=OAuth+flow+failed+—+try+again",
                                    status_code=303)
        app.state.oauth_states.discard(state)
        try:
            gmail.exchange_code(gmail.load_client(root / "data"), code,
                                _redirect_uri(request), root / "data")
            address = gmail.connect_account(conn, root / "data")
        except Exception as exc:  # noqa: BLE001 — surface, don't 500
            return RedirectResponse(f"/emails?error={quote_plus(str(exc)[:200])}",
                                    status_code=303)
        return RedirectResponse(f"/emails?connected_as={quote_plus(address)}",
                                status_code=303)

    @app.post("/emails/sync")
    def emails_sync():
        try:
            counts = gmail.sync(conn, root / "data")
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/emails?error={quote_plus(str(exc)[:200])}",
                                    status_code=303)
        synced = f"{counts['stored']}+stored+of+{counts['checked']}+checked"
        if counts.get("purged"):
            synced += f",+{counts['purged']}+old+unmatched+purged"
        return RedirectResponse(f"/emails?synced={synced}", status_code=303)

    # --------------------------------------------------------------- JSON API
    @app.get("/api/jobs")
    def api_jobs(q: str = "", stack: str = ""):
        rows = db.search_jobs(conn, q=q, stack=stack)
        return JSONResponse([dict(r) for r in rows])

    @app.get("/api/jobs/{job_id}/history")
    def api_history(job_id: int):
        rows = conn.execute(
            "SELECT event_type, payload, created_at FROM job_events "
            "WHERE job_id = ? ORDER BY created_at", (job_id,)).fetchall()
        return JSONResponse([
            {**dict(r), "payload": json.loads(r["payload"]) if r["payload"] else {}}
            for r in rows
        ])

    app.state.conn = conn  # for tests
    app.state.oauth_states = set()
    return app
