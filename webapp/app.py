"""Job-application web UI.

Run with `python -m jobsearch ui` → http://127.0.0.1:8484. Local-only by
design: the database holds profile PII and application history.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobsearch.prep.seed import seed_into_db
from jobsearch.referrals import discover as referrals_discover
from jobsearch.referrals import store as referrals_store
from jobsearch.referrals.sources.linkedin import LinkedinDiscoverer
from jobsearch.resume import extract_keywords, pdf_to_text

from jobsearch.company_questions import canonical_key

from . import clusters, company_questions, db, emailmod, gmail, ingest, prep_sources, profile
from .apply_browser import SessionRegistry
from .runner import PipelineRunner
from .textfmt import description_html, prep_markdown

HERE = Path(__file__).parent


def _safe_next(value: str) -> str:
    """Keep post-action redirects on this site — reject absolute URLs and
    scheme-relative (``//host``) values that could send the user off-origin."""
    return value if value.startswith("/") and not value.startswith("//") else "/prep"


def create_app(root: Path, db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="jobsearch UI")
    db_path = db_path or root / "data" / "jobsearch.db"
    conn = db.connect(db_path)
    profile.ensure_seeded(conn, root)
    profile.ensure_fields(conn)  # top up newly-added profile fields on old DBs
    # Load the software-interview prep curriculum into the prep_* tables. Cheap
    # and idempotent (a content hash skips the work when nothing changed); user
    # progress lives in separate tables and is never wiped.
    seed_into_db(conn)
    # Load the curated company → LeetCode question sets (idempotent; user
    # solve-progress in company_problem_progress is never wiped).
    company_questions.seed_bundled(conn)
    sessions = SessionRegistry(db_path, root / "data" / "browser_profile",
                               data_dir=root / "data")
    runner = PipelineRunner(root)
    # The startup pipeline runs the same way under its own subcommand; both
    # share the one ingest pass (ingest_latest pulls every track), so whichever
    # finishes triggers a full refresh.
    startup_runner = PipelineRunner(
        root, cmd=[sys.executable, "-u", "-m", "jobsearch", "run-startups"])
    runners = {"main": runner, "startups": startup_runner}
    app.state.runner = runner
    app.state.startup_runner = startup_runner

    # Lazy LinkedIn referral discoverer — Playwright doesn't start until the
    # first /referrals/discover request, so this adds no startup cost.
    _settings_path = root / "config" / "settings.yaml"
    _settings_raw = ((yaml.safe_load(_settings_path.read_text()) or {})
                     if _settings_path.exists() else {})
    _ref_cfg = _settings_raw.get("referrals", {}) or {}
    discoverer = LinkedinDiscoverer(
        profile_dir=root / _ref_cfg.get(
            "browser_profile_dir", "data/browser_profile/linkedin"),
        headless=bool(_ref_cfg.get("headless", False)),
        max_candidates=int(_ref_cfg.get("max_candidates", 25)),
    )

    # Guards against launching overlapping background pipeline runs.
    _pipeline_state = {"running": False}

    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["qp"] = quote_plus
    templates.env.filters["description_html"] = description_html
    templates.env.filters["prep_markdown"] = prep_markdown
    from jobsearch.utils import normalize_company_name
    templates.env.filters["normalize_company"] = normalize_company_name
    # Cache-bust the stylesheet by file mtime so CSS edits show up without a
    # manual hard-refresh (StaticFiles otherwise lets browsers serve it stale).
    templates.env.globals["css_v"] = str(int((HERE / "static" / "app.css").stat().st_mtime))
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def render(request: Request, template: str, **ctx) -> HTMLResponse:
        ctx.setdefault("counts", db.stack_counts(conn))
        ctx.setdefault("prep_counts", db.prep_overall_counts(conn))
        ctx.setdefault("company_counts", db.company_overall_counts(conn))
        return templates.TemplateResponse(request, template, ctx)

    # ------------------------------------------------------------ dashboard
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, q: str = "", company: str = "", stack: str = "",
                  near_miss: str = "1", sort_by: str = "", sort_dir: str = "",
                  min_fit: str = "", status_filter: str = "", run_scope: str = "latest",
                  startup_scope: str = ""):
        # Parse the user-supplied min-fit defensively: blank, whitespace, or
        # malformed input (e.g. "abc", "12.5.6") means "no min-fit filter"
        # rather than a 500.
        try:
            min_fit_val = float(min_fit) if min_fit.strip() else None
        except (ValueError, TypeError):
            min_fit_val = None
        # Default to the latest run so stale to-apply jobs from earlier,
        # differently-targeted runs don't pile up; run_scope=all shows everything.
        latest_at = db.latest_run_ingested_at(conn)
        since = latest_at if (run_scope == "latest" and latest_at) else ""
        jobs = db.search_jobs(conn, q=q, company=company, stack=stack,
                              include_near_miss=near_miss == "1",
                              sort_by=sort_by, sort_dir=sort_dir,
                              min_fit=min_fit_val, status_filter=status_filter,
                              since=since, startup_scope=startup_scope)
        # Startup facts for the rows shown, so the table can badge a startup and
        # surface its employees/stage inline. Only the startup rows are queried.
        startups: dict = {}
        for j in jobs:
            if j["is_startup"]:
                su = db.startup_company_for(conn, j["company"])
                if su:
                    startups[su["company_key"]] = su
        # Company filter scoped to the current section (To apply / Applied), so
        # it only lists companies with jobs there. Keep a stale selection visible.
        companies = db.companies_for_stack(conn, stack)
        if company and company not in companies:
            companies = sorted(set(companies) | {company})
        last_run = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return render(request, "dashboard.html", jobs=jobs, q=q, company=company,
                      stack=stack, near_miss=near_miss, companies=companies,
                      last_run=last_run, sort_by=sort_by, sort_dir=sort_dir,
                      min_fit=min_fit, status_filter=status_filter,
                      run_scope=run_scope, has_runs=bool(latest_at),
                      startup_scope=startup_scope, startups=startups,
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
        # The LeetCode questions this company is known to ask (top few), plus a
        # link to the full company page. Empty for companies not in the registry.
        company_key = canonical_key(job["company"])
        lc_questions = db.company_problems_for(conn, company_key, limit=6)
        lc_total = db.company_problem_count(conn, company_key)
        # Startup facts (employees, funding, investors, …) for this company when
        # it's a known startup — shown and editable in a sidebar panel.
        startup = db.startup_company_for(conn, job["company"]) if job["is_startup"] else None
        return render(request, "job_detail.html", job=job, events=events,
                      emails=emails, statuses=db.APP_STATUSES,
                      profile_fields=profile.panel_fields(conn),
                      lc_questions=lc_questions, lc_total=lc_total,
                      company_key=company_key, startup=startup)

    # ----------------------------------------------------------- referrals
    @app.get("/jobs/{job_id}/referrals", response_class=HTMLResponse)
    def job_referrals(request: Request, job_id: int):
        job = db.job_with_application(conn, job_id)
        if job is None:
            return RedirectResponse("/", status_code=303)
        candidates = referrals_store.candidates_for_job(conn, job_id)
        run = referrals_store.latest_run(conn, job_id)
        is_running = bool(run and run["state"] == "running")
        return render(request, "referrals.html", job=job,
                      candidates=candidates, run=run, is_running=is_running)

    @app.post("/jobs/{job_id}/referrals/discover")
    def trigger_referrals(job_id: int):
        # Don't queue overlapping searches for the same job — the existing
        # row stays "running" until the background worker finishes or fails.
        if referrals_store.is_running(conn, job_id):
            return RedirectResponse(f"/jobs/{job_id}/referrals", status_code=303)
        import threading
        def _go():
            # Each worker thread owns its own conn — sqlite WAL writes are
            # safer that way even with check_same_thread=False.
            worker_conn = db.connect(db_path)
            try:
                referrals_discover.discover_for_job(
                    worker_conn, root, job_id, discoverer)
            finally:
                worker_conn.close()
        threading.Thread(target=_go, daemon=True).start()
        return RedirectResponse(f"/jobs/{job_id}/referrals", status_code=303)

    # ----------------------------------------------- fit clustering visualization
    @app.get("/clusters", response_class=HTMLResponse)
    def clusters_home(request: Request, track: str = "main"):
        """High-level view: a 2-D map of every scored posting, coloured by the
        K-means cluster it landed in, with the resume plotted in the same space
        and each cluster's topic terms + resume-affinity called out. `track`
        switches between the main run and the startup run's fit map."""
        track = "startups" if track == "startups" else "main"
        clustering = clusters.load_clustering(root, track)
        ids_by_key = (db.job_ids_by_key(conn, (j["key"] for j in clustering["jobs"]))
                      if clustering else {})
        return render(request, "clusters.html", clustering=clustering, track=track,
                      has_startups=bool(clusters.load_clustering(root, "startups")),
                      points=clusters.map_points(clustering, ids_by_key))

    @app.get("/clusters/job/{job_id}", response_class=HTMLResponse)
    def cluster_job(request: Request, job_id: int):
        """Per-job view: exactly how this posting's fit score was built — the
        cosine-similarity and cluster-affinity terms, the overlapping keywords
        that drove the match, and where the posting sits on the map. A startup
        job is read from the startup run's fit map."""
        job = db.job_with_application(conn, job_id)
        if job is None:
            return RedirectResponse("/clusters", status_code=303)
        track = "startups" if job["is_startup"] else "main"
        clustering = clusters.load_clustering(root, track)
        breakdown = clusters.job_breakdown(clustering, job["key"])
        cluster = clusters.cluster_by_id(clustering, breakdown["cluster"]) if breakdown else None
        ids_by_key = (db.job_ids_by_key(conn, (j["key"] for j in clustering["jobs"]))
                      if clustering else {})
        return render(request, "cluster_job.html", job=job, clustering=clustering,
                      track=track, breakdown=breakdown, cluster=cluster,
                      points=clusters.map_points(clustering, ids_by_key))

    # ------------------------------------------------------------ startups
    @app.get("/startups", response_class=HTMLResponse)
    def startups_directory(request: Request, q: str = ""):
        """The startup directory: every tracked startup with its helpful facts
        (employees, funding, investors, notable people) and open-job counts.
        Editable per company; populated by `discover-startups` + ingest."""
        rows = db.list_startups(conn, q=q)
        startup_clustering = bool(clusters.load_clustering(root, "startups"))
        return render(request, "startups.html", startups=rows, q=q,
                      has_startup_fitmap=startup_clustering,
                      counts_startup=db.stack_counts(conn))

    @app.get("/startups/{company_key}", response_class=HTMLResponse)
    def startup_detail(request: Request, company_key: str):
        startup = db.startup_company(conn, company_key)
        if startup is None:
            return RedirectResponse("/startups", status_code=303)
        jobs = db.search_jobs(conn, company=startup["name"], startup_scope="only")
        return render(request, "startup_detail.html", startup=startup, jobs=jobs)

    @app.post("/startups/{company_key}/edit")
    async def edit_startup(company_key: str, request: Request):
        """Save manual edits to a startup's facts. Sets the user_edited guard so
        a later ingest never clobbers what you typed."""
        form = await request.form()
        existing = db.startup_company(conn, company_key)
        if existing is None:
            return RedirectResponse("/startups", status_code=303)
        meta = {"name": existing["name"]}
        for field in db.STARTUP_SCALAR:
            meta[field] = (form.get(field) or "").strip()
        for field in db.STARTUP_LIST:
            # comma- or newline-separated → list
            raw = (form.get(field) or "").replace("\n", ",")
            meta[field] = [p.strip() for p in raw.split(",") if p.strip()]
        for field in db.STARTUP_BOOL:
            meta[field] = form.get(field) in ("1", "on", "true")
        db.upsert_startup_company(conn, meta, from_user=True)
        return RedirectResponse(f"/startups/{quote_plus(company_key)}", status_code=303)

    # ------------------------------------------------- interview prep
    def _resume_disciplines() -> list[str]:
        """The prep disciplines the current resume maps to, used to highlight
        relevant tracks on /prep. Best-effort and offline — returns [] when
        there's no resume or no confident occupation match (then the page shows
        the full catalog without singling anything out)."""
        try:
            from jobsearch.config import load_settings
            from jobsearch.prep.disciplines import disciplines_for_occupations
            from jobsearch.resume import load_resume_text
            from jobsearch.role_profile import resolve_profile
            settings = load_settings(root / "config" / "settings.yaml")
            resume_text, _ = load_resume_text(root, settings)
            profile = resolve_profile(root, settings, resume_text)
            return disciplines_for_occupations(profile.occupations) if profile else []
        except Exception:  # noqa: BLE001 — prep must render even if matching hiccups
            return []

    def _split_prep_tracks(tracks: list[dict], disciplines: list[str]):
        """Attach each track's disciplines (from the authored content) and split
        into (recommended_for_resume, other)."""
        from jobsearch.prep import ALL_TRACKS
        from jobsearch.prep.disciplines import split_tracks
        by_slug = {t["slug"]: (t.get("disciplines") or []) for t in ALL_TRACKS}
        for row in tracks:
            row["disciplines"] = by_slug.get(row["slug"], [])
        return split_tracks(tracks, disciplines)

    @app.get("/prep", response_class=HTMLResponse)
    def prep_home(request: Request):
        tracks = db.prep_tracks_overview(conn)
        disciplines = _resume_disciplines()
        recommended, other = _split_prep_tracks(tracks, disciplines)
        return render(request, "prep.html",
                      tracks=tracks,
                      recommended_tracks=recommended,
                      other_tracks=other,
                      resume_disciplines=disciplines,
                      resume_target=db.prep_resume_target(conn),
                      overall=db.prep_overall_counts(conn),
                      companies=db.companies_overview(conn))

    @app.get("/prep/track/{track_slug}", response_class=HTMLResponse)
    def prep_track(request: Request, track_slug: str):
        track = conn.execute(
            "SELECT * FROM prep_tracks WHERE slug = ?", (track_slug,)).fetchone()
        if track is None:
            return RedirectResponse("/prep", status_code=303)
        return render(request, "prep_track.html", track=dict(track),
                      modules=db.prep_modules_for_track(conn, track["id"]))

    @app.get("/prep/module/{module_slug}", response_class=HTMLResponse)
    def prep_module(request: Request, module_slug: str):
        detail = db.prep_module_detail(conn, module_slug)
        if detail is None:
            return RedirectResponse("/prep", status_code=303)
        detail["has_source"] = prep_sources.available(root, detail["module"]["source_refs"])
        return render(request, "prep_module.html", **detail)

    @app.get("/prep/module/{module_slug}/source", response_class=HTMLResponse)
    def prep_module_source(request: Request, module_slug: str):
        row = conn.execute(
            """SELECT m.*, t.slug AS track_slug, t.title AS track_title
               FROM prep_modules m JOIN prep_tracks t ON t.id = m.track_id
               WHERE m.slug = ?""", (module_slug,)).fetchone()
        if row is None:
            return RedirectResponse("/prep", status_code=303)
        info = prep_sources.source_for(root, row["source_refs"])
        text = ""
        if info and info["has_text"]:
            text = prep_sources.chapter_markdown(info["text_path"])
        return render(request, "prep_source.html", module=dict(row), info=info, text=text)

    @app.get("/prep/book/{book_key}")
    def prep_book(book_key: str):
        pdf = prep_sources.pdf_path(root, book_key)
        if pdf is None:
            return JSONResponse(
                {"error": "book PDF not available locally (kept in prep_work/)"},
                status_code=404)
        # Inline so the browser's PDF viewer honours the #page=N anchor.
        return FileResponse(str(pdf), media_type="application/pdf",
                            headers={"Content-Disposition": "inline"})

    @app.get("/prep/module/{module_slug}/lesson/{lesson_slug}", response_class=HTMLResponse)
    def prep_lesson(request: Request, module_slug: str, lesson_slug: str):
        detail = db.prep_lesson_detail(conn, module_slug, lesson_slug)
        if detail is None:
            return RedirectResponse("/prep", status_code=303)
        lesson = detail["lesson"]
        # Opening a fresh lesson marks it in-progress so the /prep landing can
        # resume you here. Already-completed lessons are left as-is.
        if lesson["state"] == "not_started":
            db.set_lesson_state(conn, lesson["id"], "in_progress")
            lesson["state"] = "in_progress"
        try:
            takeaways = json.loads(lesson.get("key_takeaways") or "[]")
        except (ValueError, TypeError):
            takeaways = []
        mod = conn.execute("SELECT source_refs FROM prep_modules WHERE slug = ?",
                           (module_slug,)).fetchone()
        has_source = prep_sources.available(root, mod["source_refs"]) if mod else False
        return render(request, "prep_lesson.html", lesson=lesson,
                      siblings=detail["siblings"], takeaways=takeaways,
                      has_source=has_source)

    @app.post("/prep/lessons/{lesson_id}/state")
    def prep_set_lesson(lesson_id: int, state: str = Form(...),
                        notes: str = Form(None), next: str = Form("/prep")):
        try:
            db.set_lesson_state(conn, lesson_id, state, notes=notes)
        except ValueError:
            pass
        return RedirectResponse(_safe_next(next), status_code=303)

    @app.post("/prep/problems/{problem_id}/state")
    def prep_set_problem(problem_id: int, state: str = Form(...),
                         next: str = Form("/prep")):
        try:
            db.set_problem_state(conn, problem_id, state)
        except ValueError:
            pass
        return RedirectResponse(_safe_next(next), status_code=303)

    @app.get("/prep/module/{module_slug}/ctci/{problem_slug}", response_class=HTMLResponse)
    def prep_ctci_problem(request: Request, module_slug: str, problem_slug: str):
        detail = db.prep_ctci_problem_detail(conn, module_slug, problem_slug)
        if detail is None:
            return RedirectResponse(f"/prep/module/{module_slug}", status_code=303)
        problem = detail["problem"]
        if problem["state"] == "not_started":
            db.set_ctci_problem_state(conn, problem["id"], "attempted")
            problem["state"] = "attempted"
        try:
            hints = json.loads(problem.get("hints") or "[]")
        except (ValueError, TypeError):
            hints = []
        return render(request, "prep_problem.html", problem=problem,
                      siblings=detail["siblings"], hints=hints)

    @app.post("/prep/ctci-problems/{ctci_problem_id}/state")
    def prep_set_ctci_problem(ctci_problem_id: int, state: str = Form(...),
                              notes: str = Form(None), next: str = Form("/prep")):
        try:
            db.set_ctci_problem_state(conn, ctci_problem_id, state, notes=notes)
        except ValueError:
            pass
        return RedirectResponse(_safe_next(next), status_code=303)

    # ----------------------------------------------- company LeetCode questions
    @app.get("/companies", response_class=HTMLResponse)
    def companies_home(request: Request):
        # render() already injects company_counts (used by the nav badge and the
        # page header), so no need to recompute it here.
        return render(request, "companies.html",
                      companies=db.companies_overview(conn))

    @app.get("/companies/{company_key}", response_class=HTMLResponse)
    def company_detail(request: Request, company_key: str, difficulty: str = ""):
        problems = db.company_problems_for(conn, company_key, difficulty=difficulty)
        # The empty state (unknown company / no problems) is handled in-template
        # with a "⟳ Refresh questions" CTA, so no special-casing is needed here.
        return render(request, "company.html",
                      company=db.company_display_name(conn, company_key),
                      company_key=company_key, problems=problems,
                      difficulty=difficulty,
                      run=db.latest_company_refresh(conn, company_key),
                      is_running=db.company_refresh_running(conn, company_key),
                      all_problem_count=db.company_problem_count(conn, company_key))

    def _start_refresh(company: str, company_key: str) -> bool:
        if db.company_refresh_running(conn, company_key):
            return False
        import threading

        def _go():
            worker_conn = db.connect(db_path)
            try:
                company_questions.run_refresh(worker_conn, root, company, company_key)
            finally:
                worker_conn.close()
        threading.Thread(target=_go, daemon=True).start()
        return True

    @app.post("/companies/{company_key}/refresh")
    def refresh_company(company_key: str, company: str = Form("")):
        name = company or db.company_display_name(conn, company_key)
        _start_refresh(name, company_key)
        return RedirectResponse(f"/companies/{company_key}", status_code=303)

    @app.post("/company-problems/{problem_id}/state")
    def set_company_problem(problem_id: int, state: str = Form(...),
                            next: str = Form("/companies")):
        try:
            db.set_company_problem_state(conn, problem_id, state)
        except (ValueError, sqlite3.Error):
            # Bad state value, or a stale id whose problem row is gone (the
            # progress FK fails) — ignore and redirect rather than 500.
            pass
        return RedirectResponse(_safe_next(next), status_code=303)

    @app.get("/api/companies/{company_key}/refresh-status")
    def company_refresh_status(company_key: str):
        run = db.latest_company_refresh(conn, company_key)
        return JSONResponse({
            "running": db.company_refresh_running(conn, company_key),
            "state": run["state"] if run else "",
            "detail": run["detail"] if run else "",
            "problem_count": len(db.company_problems_for(conn, company_key)),
        })

    # --------------------------------------------------------------- actions
    @app.post("/jobs/{job_id}/apply")
    def apply(job_id: int):
        job = db.job_with_application(conn, job_id)
        if job is None or not job["url"]:
            return JSONResponse({"error": "job or url missing"}, status_code=404)
        session = sessions.launch(job["application_id"], job["url"])
        return JSONResponse({"state": session.state})

    @app.post("/jobs/{job_id}/refill")
    def refill(job_id: int):
        # Re-run auto-fill on this job's already-open tab (or open one if none).
        job = db.job_with_application(conn, job_id)
        if job is None or not job["url"]:
            return JSONResponse({"error": "job or url missing"}, status_code=404)
        session = sessions.refill(job["application_id"], job["url"])
        return JSONResponse({"state": session.state})

    @app.get("/api/apply-status/{application_id}")
    def apply_status(application_id: int):
        status = sessions.status(application_id)  # includes the fill summary
        row = conn.execute("SELECT status FROM applications WHERE id = ?",
                           (application_id,)).fetchone()
        status["application_status"] = row["status"] if row else "unknown"
        return JSONResponse(status)

    @app.post("/api/apply-all")
    def apply_all():
        # Fill every job tab already open in the integrated browser.
        return JSONResponse(sessions.apply_all())

    @app.get("/api/apply-all-status")
    def apply_all_status():
        return JSONResponse({"sessions": sessions.all_statuses()})

    @app.post("/api/prepare-top")
    def prepare_top(n: int = 5):
        # Pick the n best-fit applyable jobs and open+auto-fill a tab for each.
        launched = []
        for job in db.top_fit_to_apply(conn, n):
            session = sessions.launch(job["application_id"], job["url"])
            launched.append({"application_id": job["application_id"],
                             "company": job["company"], "title": job["title"],
                             "state": session.state})
        return JSONResponse({"count": len(launched), "launched": launched})

    @app.post("/applications/bulk-status")
    async def bulk_status(request: Request):
        # Batch-set status (e.g. "applied") for the checked rows, then return to
        # the same filtered view so the rows move into the right section.
        form = await request.form()
        status = form.get("status", "applied")
        ids = form.getlist("application_id")
        if status in db.APP_STATUSES:
            for raw in ids:
                # Skip bad/stale ids (non-int, or an id with no application row →
                # a FK IntegrityError) without aborting the rest of the batch.
                try:
                    db.set_application_status(conn, int(raw), status,
                                              detail="bulk action", via="ui")
                except (ValueError, TypeError, sqlite3.Error):
                    continue
        return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

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
    def start_pipeline(track: str = "main"):
        active = runners.get(track, runner)
        started = active.start()
        return JSONResponse({"started": started, "track": track},
                            status_code=200 if started else 409)

    @app.get("/run/log")
    def pipeline_log(since: int = 0, track: str = "main"):
        active = runners.get(track, runner)
        # Seamless finish: first poll after a successful run ingests the fresh
        # reports (every track) so the dashboard fills without a separate click.
        if active.exit_code == 0 and not active.running and not active.ingested:
            active.ingested = True
            try:
                counts = ingest.ingest_latest(root, conn)
                msg = (f"Ingested into UI: {counts['inserted']} new, "
                       f"{counts['updated']} updated jobs.")
                if counts.get("startups_loaded"):
                    msg += f" {counts['startups_loaded']} startup profiles."
                active.lines.append(msg + " Refresh the dashboard.")
                stale = counts.get("stale_unapplied", 0)
                if stale:
                    active.lines.append(
                        f"Heads up: {stale} unapplied job(s) on the dashboard are "
                        "from earlier runs (not in this report) — likely a previous "
                        "role target. Filter or clear them to see only this run.")
            except Exception as exc:  # noqa: BLE001 — surface in the log panel
                active.lines.append(f"Ingest failed: {exc}")
        return JSONResponse(active.snapshot(since))

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
        max_bytes = 10 * 1024 * 1024  # cap the read so a huge upload can't OOM us
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            return RedirectResponse(
                f"/resume?error={quote_plus('file too large (max 10 MB)')}",
                status_code=303)
        name = (file.filename or "").lower()
        try:
            if name.endswith(".pdf"):
                if not data.startswith(b"%PDF"):
                    raise ValueError("that file isn't a valid PDF")
                text = pdf_to_text(data)
                (root / "data" / "resume.pdf").write_bytes(data)
                # Remember the original filename so auto-apply attaches the
                # resume under the same name the user uploaded.
                (root / "data" / "resume.pdf.name").write_text(
                    Path(file.filename or "resume.pdf").name)
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
        return render(request, "profile.html", fields=profile.all_fields(conn),
                      field_options=profile.FIELD_OPTIONS)

    @app.post("/profile")
    async def save_profile(request: Request):
        form = await request.form()
        for field, value in form.items():
            profile.set_field(conn, field, str(value))
        return RedirectResponse("/profile", status_code=303)

    @app.post("/profile/from-resume")
    def profile_from_resume():
        # Fill empty profile fields from the resume; never clobbers manual edits.
        resume = root / "data" / "resume.txt"
        if resume.exists():
            profile.populate_from_resume(conn, resume.read_text())
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
