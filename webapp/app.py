"""Job-application web UI.

Run with `python -m jobsearch ui` → http://127.0.0.1:8484. Local-only by
design: the database holds profile PII and application history.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, emailmod, ingest, profile
from .apply_browser import SessionRegistry

HERE = Path(__file__).parent


def create_app(root: Path, db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="jobsearch UI")
    db_path = db_path or root / "data" / "jobsearch.db"
    conn = db.connect(db_path)
    profile.ensure_seeded(conn, root)
    sessions = SessionRegistry(db_path, root / "data" / "browser_profile")

    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def render(request: Request, template: str, **ctx) -> HTMLResponse:
        ctx.setdefault("counts", db.stack_counts(conn))
        return templates.TemplateResponse(request, template, ctx)

    # ------------------------------------------------------------ dashboard
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, q: str = "", company: str = "", stack: str = "",
                  near_miss: str = "1"):
        jobs = db.search_jobs(conn, q=q, company=company, stack=stack,
                              include_near_miss=near_miss == "1")
        companies = [r["company"] for r in conn.execute(
            "SELECT DISTINCT company FROM jobs ORDER BY company").fetchall()]
        last_run = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return render(request, "dashboard.html", jobs=jobs, q=q, company=company,
                      stack=stack, near_miss=near_miss, companies=companies,
                      last_run=last_run)

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
        status = sessions.status(application_id)
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

    @app.post("/ingest")
    def do_ingest():
        try:
            counts = ingest.ingest_latest(root, conn)
        except FileNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return RedirectResponse(f"/?ingested={counts['inserted']}", status_code=303)

    # ------------------------------------------------------- resume & profile
    @app.get("/resume", response_class=HTMLResponse)
    def resume(request: Request):
        text_path = root / "data" / "resume.txt"
        resume_text = text_path.read_text() if text_path.exists() else ""
        pdfs = sorted((root / "data").glob("*.pdf"))
        # Sections split on blank lines for per-block copy buttons.
        sections = [s.strip() for s in resume_text.split("\n\n") if s.strip()]
        return render(request, "resume.html", resume_text=resume_text,
                      sections=sections, pdf_name=pdfs[-1].name if pdfs else "")

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
    def emails_page(request: Request, q: str = ""):
        connected = emailmod.is_connected(conn)
        sql = """SELECT m.*, j.company AS job_company, j.title AS job_title
                 FROM email_messages m LEFT JOIN jobs j ON j.id = m.job_id"""
        args: list = []
        if q:
            sql += " WHERE m.subject LIKE ? OR m.from_addr LIKE ? OR m.body LIKE ?"
            args = [f"%{q}%"] * 3
        sql += " ORDER BY m.sent_at DESC LIMIT 200"
        messages = conn.execute(sql, args).fetchall()
        return render(request, "emails.html", connected=connected, messages=messages,
                      q=q, setup=emailmod.SETUP_INSTRUCTIONS)

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
    return app
