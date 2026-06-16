"""Integrated application browser: multi-tab, auto-filling.

One persistent headed Chromium (profile under data/browser_profile/, so ATS
logins survive) is shared by every apply session — each "Auto-fill apply"
click opens a new tab in the same window, so several applications can be
worked in parallel. A single daemon thread (BrowserHost) owns the Playwright
sync API and drives all tabs by polling:

  open tab → navigate → page settles → auto-fill pass (webapp/autofill.py)
  → report what was filled/skipped → user reviews and submits → confirmation
  page detected → application marked applied.

A new fill pass runs every time a tab's URL changes (multi-step ATS flows
like Workday). The engine NEVER clicks submit — getting the form filled and
leaving the final review + submit to the user is the contract
(docs/design-autofill.md).

State is communicated through the database plus an in-memory registry the
UI polls via /api/apply-status.
"""

from __future__ import annotations

import queue
import re
import sys
import threading
from pathlib import Path

from . import ats, autofill, db
from . import profile as profilemod

# Heuristics for "your application was submitted" pages. Deliberately
# conservative: a false 'applied' is worse than asking the user to confirm.
CONFIRM_URL = re.compile(r"(confirmation|thank[-_]?you|application[-_/]?(submitted|complete|received))", re.I)
CONFIRM_TEXT = re.compile(
    r"(application (has been |was )?(submitted|received|complete)"
    r"|thank you for (applying|your application)"
    r"|we('ve| have) received your application)",
    re.I,
)

PLAYWRIGHT_MISSING = ("playwright not installed — pip install playwright "
                      "&& playwright install chromium")

# A React application form hydrates over several frames; keep re-filling the
# same URL until the control count holds steady for STABLE_PASSES passes, or we
# hit MAX_FILL_PASSES (a backstop so a churning page can't loop forever).
MAX_FILL_PASSES = 8
STABLE_PASSES = 2


def looks_like_confirmation(url: str, title: str = "", body_text: str = "") -> bool:
    if CONFIRM_URL.search(url or ""):
        return True
    return bool(CONFIRM_TEXT.search(f"{title}\n{body_text or ''}"[:20000]))


class ApplySession:
    """State holder for one application's tab; driven by the BrowserHost."""

    def __init__(self, application_id, job_url: str, *, page=None, adopted: bool = False):
        # application_id may be None for an adopted tab that matched no tracked
        # job — it still gets filled, just without DB status updates.
        self.application_id = application_id
        self.adopted = adopted       # bound to a tab the user already opened
        # Adopted tabs are filled where they are (no canonicalize/navigate); the
        # settle loop's iframe-hoist/apply-gate still reaches the real form.
        self.job_url = job_url if adopted else ats.canonical_apply_url(job_url)
        self.platform = ats.detect_platform(self.job_url)
        self.state = "open" if adopted else "starting"
        self.detail = ""
        self.fill = {"filled": 0, "skipped": 0, "fields": [], "notes": []}
        self.page = page             # owned by the BrowserHost thread
        self.last_url = ""
        self.settled = False
        self.advanced = False        # already tried iframe-hoist / apply-gate once
        self.cf_blocked = False      # waiting on a Cloudflare challenge to clear
        self.schema: dict | None = None  # Greenhouse field schema (fetched lazily)
        # Multi-pass fill state — application forms are React SPAs that hydrate
        # progressively, so we re-fill the same URL until it stops growing.
        self.fill_url = ""           # URL the pass tracker is following
        self.fill_passes = 0
        self.fill_stable = 0         # consecutive passes with no new fields
        self.last_fillable = -1
        self.done_keys: set[str] = set()   # controls already handled (any pass)
        self.done_urls: set[str] = set()   # URLs whose form has stabilised

    @property
    def live(self) -> bool:
        return self.page is not None and self.state in ("starting", "open", "applied")

    def status(self) -> dict:
        return {"state": self.state, "detail": self.detail, "fill": self.fill}


class BrowserHost(threading.Thread):
    """The single thread that owns Playwright and every apply tab."""

    def __init__(self, db_path: Path, profile_dir: Path, data_dir: Path):
        super().__init__(daemon=True, name="apply-browser")
        self.db_path = db_path
        self.profile_dir = profile_dir
        self.data_dir = data_dir
        self._queue: queue.Queue[ApplySession] = queue.Queue()
        self.sessions: dict[int, ApplySession] = {}
        self._context = None          # the live persistent context (host thread)
        self._adopt = threading.Event()  # request: fill every open tab
        self._refill: queue.Queue[int] = queue.Queue()  # request: re-fill one tab
        self._synthetic = 0           # ids for adopted tabs with no tracked job
        self._resume_cache: dict | None = None  # resume-derived fallback values

    def open_tab(self, session: ApplySession) -> None:
        self.sessions[session.application_id] = session
        self._queue.put(session)

    def request_apply_all(self) -> None:
        """Ask the host thread to adopt and fill every open job tab. Setting an
        event (not touching pages here) keeps Playwright on its owning thread."""
        self._adopt.set()

    def request_refill(self, application_id: int) -> None:
        """Ask the host to re-run auto-fill on an existing tab (host thread does
        the page work)."""
        self._refill.put(application_id)

    def _next_synthetic_id(self) -> int:
        self._synthetic -= 1
        return self._synthetic

    def _resume_fields(self) -> dict:
        """Resume-derived values, parsed once, used as a fallback under the
        profile so empty profile fields still fill from the resume."""
        if self._resume_cache is None:
            resume = self.data_dir / "resume.txt"
            self._resume_cache = (profilemod.seed_from_resume(resume.read_text())
                                  if resume.exists() else {})
        return self._resume_cache

    # ------------------------------------------------------------- main loop
    def run(self) -> None:  # noqa: C901 — the event loop is one coherent unit
        conn = db.connect(self.db_path)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            while True:  # report the actionable error to every request
                self._queue.get().state = "error"
                for s in self.sessions.values():
                    if s.state == "error" and not s.detail:
                        s.detail = PLAYWRIGHT_MISSING
        with sync_playwright() as p:
            self._context = None
            while True:
                try:
                    session = self._queue.get(timeout=0.5)
                except queue.Empty:
                    session = None
                if session is not None:
                    try:
                        if self._context is None:
                            self._context = p.chromium.launch_persistent_context(
                                user_data_dir=str(self.profile_dir),
                                headless=False, viewport=None,
                                args=["--start-maximized"],
                            )
                        session.page = self._fresh_page(self._context)
                        session.state = "open"
                        db.set_application_status(
                            conn, session.application_id, "in_progress",
                            detail=f"opened {session.job_url}", via="integrated_browser")
                        session.page.goto(session.job_url, wait_until="domcontentloaded")
                    except Exception as exc:  # noqa: BLE001
                        session.state, session.detail = "error", str(exc)[:300]
                        self._context = self._context_if_alive(self._context)
                if self._adopt.is_set():
                    self._adopt.clear()
                    try:
                        self._adopt_open_tabs(conn)
                    except Exception:  # noqa: BLE001
                        pass
                while not self._refill.empty():
                    app_id = self._refill.get()
                    s = self.sessions.get(app_id)
                    if s is not None and s.page is not None:
                        self._reset_for_refill(s)
                for s in list(self.sessions.values()):
                    if not s.live:
                        continue
                    try:
                        self._tick(s, conn)
                    except Exception:  # noqa: BLE001 — page/context may vanish anytime
                        pass
                if self._context is not None and not self._context_pages(self._context):
                    try:
                        self._context.close()
                    except Exception:  # noqa: BLE001
                        pass
                    self._context = None

    # ------------------------------------------------------------ tab driver
    def _tick(self, s: ApplySession, conn) -> None:
        page = s.page
        if page.is_closed():
            s.page = None
            if s.state == "open":
                s.state = "closed"
                s.detail = "tab closed without a detected confirmation"
            return
        if page.url != s.last_url:
            s.last_url, s.settled = page.url, False
        if s.settled:
            return
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2500)
        except Exception:  # noqa: BLE001 — still loading; retry next tick
            return
        s.settled = True
        self._on_settle(s, page, conn)

    def _on_settle(self, s: ApplySession, page, conn) -> None:
        # Cloudflare interstitial: surface it and keep polling. The challenge
        # reloads the SAME url, so a URL change can't re-trigger the fill —
        # drive the resume off the cf_blocked flag instead.
        if ats.is_cloudflare_challenge(page):
            if not s.cf_blocked:
                s.cf_blocked = True
                s.detail = ("Cloudflare check — solve it in the open browser tab; "
                            "auto-fill resumes automatically")
                self._track(conn, s, "in_progress",
                            detail="waiting on Cloudflare challenge", via="integrated_browser")
            s.settled = False  # re-check next tick until the challenge clears
            return
        if s.cf_blocked:  # just cleared — restart the fill for this page
            s.cf_blocked = False
            s.detail = "Cloudflare cleared"
            s.fill_url = ""
            s.done_urls.discard(page.url)

        title, body = "", ""
        try:
            title = page.title()
            if not CONFIRM_URL.search(page.url):
                body = page.inner_text("body", timeout=2000)[:20000]
        except Exception:  # noqa: BLE001
            pass
        if s.state != "applied" and looks_like_confirmation(page.url, title, body):
            s.state, s.detail = "applied", page.url
            self._track(conn, s, "applied",
                        detail=f"confirmation detected at {page.url}", via="integrated_browser")
            return
        if s.state == "applied":
            return

        # A new URL (or a fresh start) resets the multi-pass tracker.
        if page.url != s.fill_url:
            s.fill_url = page.url
            s.fill_passes = 0
            s.fill_stable = 0
            s.last_fillable = -1
        if page.url in s.done_urls:
            return

        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        if s.fill_passes == 0:  # let the SPA hydrate before the first pass
            self._wait_form_ready(page)

        prof = {r["field"]: r["value"] for r in profilemod.all_fields(conn)}
        resume = self._resume_path()
        schema = self._greenhouse_schema(s, page)
        result = autofill.run_fill(page, prof, resume, schema=schema, done_keys=s.done_keys,
                                   resume_fields=self._resume_fields(),
                                   resume_name=self._resume_name())
        s.fill_passes += 1

        # Not a fillable form yet — either a cross-origin ATS iframe (common on
        # company-branded boards) or a posting page behind an Apply gate. Try
        # once to reach the real form; the next tick picks it up.
        if result["fillable"] < 2 and not s.advanced:
            s.advanced = True
            iframe_src = ats.ats_form_iframe_src(page)
            if iframe_src and iframe_src != page.url:
                try:
                    page.goto(iframe_src, wait_until="domcontentloaded")
                except Exception:  # noqa: BLE001
                    pass
                s.settled = False
                return
            if autofill.click_apply_button(page):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=4000)
                except Exception:  # noqa: BLE001
                    pass
                s.settled = False
                return

        self._merge_fill(s, result, conn)

        # Keep passing until the form stops growing (hydration done) or capped.
        if result["fillable"] > s.last_fillable or result["filled"]:
            s.fill_stable = 0
        else:
            s.fill_stable += 1
        s.last_fillable = max(s.last_fillable, result["fillable"])
        if s.fill_passes < MAX_FILL_PASSES and s.fill_stable < STABLE_PASSES:
            s.settled = False  # re-tick → another pass on the same URL
            return
        s.done_urls.add(page.url)

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _fresh_page(context):
        pages = context.pages
        if len(pages) == 1 and pages[0].url == "about:blank":
            return pages[0]  # reuse the launch tab
        return context.new_page()

    @staticmethod
    def _context_pages(context) -> list:
        try:
            return context.pages
        except Exception:  # noqa: BLE001
            return []

    def _context_if_alive(self, context):
        return context if context is not None and self._context_pages(context) else None

    def _resume_path(self) -> str:
        # The upload route always writes resume.pdf, so prefer it — don't guess
        # among arbitrary PDFs in data/. Fall back to any PDF only if it's gone.
        canonical = self.data_dir / "resume.pdf"
        if canonical.exists():
            return str(canonical)
        pdfs = sorted(self.data_dir.glob("*.pdf"))
        return str(pdfs[-1]) if pdfs else ""

    def _resume_name(self) -> str:
        """The original filename the user uploaded (saved alongside resume.pdf),
        so the form attaches it under that name instead of 'resume.pdf'."""
        sidecar = self.data_dir / "resume.pdf.name"
        if sidecar.exists():
            name = sidecar.read_text().strip()
            if name:
                return name
        path = self._resume_path()
        return Path(path).name if path else ""

    @staticmethod
    def _wait_form_ready(page) -> None:
        """Before the first pass, give a React form a chance to hydrate its
        custom widgets — these mount after the server-rendered text inputs and
        are exactly what the early single pass used to miss. Best-effort; a form
        with no comboboxes just falls through to the multi-pass loop."""
        try:
            page.wait_for_selector('[role="combobox"]', state="attached", timeout=4000)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _reset_for_refill(s: ApplySession) -> None:
        """Wipe a session's fill bookkeeping so the next tick re-runs a fresh
        multi-pass fill on the current page (e.g. after a profile edit)."""
        s.done_urls.clear()
        s.done_keys.clear()
        s.fill_url = ""
        s.fill_passes = 0
        s.fill_stable = 0
        s.last_fillable = -1
        s.advanced = False
        s.settled = False
        s.fill = {"filled": 0, "skipped": 0, "fields": [], "notes": []}
        if s.state in ("closed", "applied"):
            s.state = "open"

    @staticmethod
    def _merge_fill(s: ApplySession, result: dict, conn) -> None:
        """Fold a pass into the session tally as a UNION (passes are cumulative,
        not additive). 'Left for review' is the latest pass's real skips —
        already-filled controls are excluded so the count reflects what's left."""
        new_fields = []
        for f in result["fields"]:  # dedupe within the pass and against prior passes
            if f not in s.fill["fields"] and f not in new_fields:
                new_fields.append(f)
        s.fill["fields"] += new_fields
        s.fill["filled"] = len(s.fill["fields"])
        left = [x for x in result["skipped"] if x["note"] != "already filled"]
        s.fill["skipped"] = len(left)
        s.fill["notes"] = [f"{x['field']}: {x['note']}" for x in left][:30]
        if new_fields:
            BrowserHost._track(
                conn, s, "in_progress",
                detail=("auto-filled " + ", ".join(s.fill["fields"][:20])
                        + (f" (+{s.fill['skipped']} left for review)" if s.fill["skipped"] else "")),
                via="autofill")
            print(f"autofill app {s.application_id}: +{len(new_fields)} "
                  f"(total {s.fill['filled']}), {s.fill['skipped']} left", file=sys.stderr)

    def _adopt_open_tabs(self, conn) -> None:
        """Bind every qualifying already-open tab to a session so the tick loop
        fills it. Skips tabs already being filled, and tabs that are neither a
        known ATS nor a tracked job (never type into a stray Gmail/search tab)."""
        if self._context is None:
            return
        owned = {s.page for s in self.sessions.values() if s.page is not None and s.live}
        adopted = 0
        for page in self._context_pages(self._context):
            try:
                url = page.url
            except Exception:  # noqa: BLE001
                continue
            if page in owned or not url.startswith(("http://", "https://")):
                continue
            app_id = self._match_application(conn, url)
            if app_id is None and ats.detect_platform(url) == ats.CUSTOM:
                continue  # unrecognised page — leave it alone
            if app_id is not None:
                existing = self.sessions.get(app_id)
                if existing is not None and existing.live:
                    continue  # already being filled from a single-apply click
            else:
                app_id = self._next_synthetic_id()
            self.sessions[app_id] = ApplySession(app_id, url, page=page, adopted=True)
            adopted += 1
        print(f"apply-all: adopted {adopted} open tab(s)", file=sys.stderr)

    @staticmethod
    def _match_application(conn, url: str):
        """Map an open tab's URL to a tracked application_id (exact URL, then
        Greenhouse job-id — the open embed form and the stored branded URL share
        the gh job id). None if unmatched."""
        row = db.application_by_url(conn, url)
        if row is not None:
            return row["application_id"]
        job_id = ats.greenhouse_job_id(url)
        if not job_id:
            return None
        for cand in db.active_application_urls(conn):
            if ats.greenhouse_job_id(cand["url"] or "") == job_id:
                return cand["application_id"]
        return None

    @staticmethod
    def _track(conn, s: ApplySession, status: str, detail: str = "", via: str = "") -> None:
        """Write application status only for real, tracked applications —
        adopted tabs with no matched job (synthetic negative id) just get filled."""
        if s.application_id and s.application_id > 0:
            db.set_application_status(conn, s.application_id, status, detail=detail, via=via)

    @staticmethod
    def _greenhouse_schema(s: ApplySession, page) -> dict | None:
        """Fetch the Greenhouse field schema once we're on a parseable URL.
        Retries each settle (cheap — no network until a board+id is parsed) so
        a branded page that hoists into the embed still gets enriched."""
        if s.platform != ats.GREENHOUSE or s.schema is not None:
            return s.schema
        s.schema = (ats.greenhouse_schema_for(page.url)
                    or ats.greenhouse_schema_for(s.job_url))
        return s.schema


class SessionRegistry:
    """One live session per application, any number live at once — each gets
    its own tab in the shared browser. The UI polls /api/apply-status."""

    def __init__(self, db_path: Path, profile_dir: Path, data_dir: Path | None = None):
        self.db_path = db_path
        self.profile_dir = profile_dir
        self.data_dir = data_dir or profile_dir.parent
        self._host: BrowserHost | None = None
        self._lock = threading.Lock()

    def _ensure_host(self) -> BrowserHost:
        if self._host is None or not self._host.is_alive():
            old_sessions = self._host.sessions if self._host else {}
            self._host = BrowserHost(self.db_path, self.profile_dir, self.data_dir)
            self._host.sessions.update(old_sessions)
            self._host.start()
        return self._host

    def launch(self, application_id: int, job_url: str) -> ApplySession:
        with self._lock:
            host = self._ensure_host()
            existing = host.sessions.get(application_id)
            if existing and existing.state in ("starting", "open"):
                return existing
            session = ApplySession(application_id, job_url)
            host.open_tab(session)
            return session

    def status(self, application_id: int) -> dict:
        session = self._host.sessions.get(application_id) if self._host else None
        if not session:
            return {"state": "none", "detail": "", "fill": {}}
        return session.status()

    def refill(self, application_id: int, job_url: str) -> ApplySession:
        """Re-run auto-fill on this application's open tab. If no live tab
        exists, fall back to opening one (same as a fresh apply)."""
        with self._lock:
            host = self._host if (self._host and self._host.is_alive()) else None
            session = host.sessions.get(application_id) if host else None
            # Only attribute reads here — page work stays on the host thread.
            if host and session and session.page is not None \
                    and session.state in ("open", "applied"):
                host.request_refill(application_id)
                return session
        return self.launch(application_id, job_url)

    def apply_all(self) -> dict:
        """Ask the host to fill every open job tab. Only meaningful once the
        integrated browser is open (a prior apply bootstraps it) with tabs in
        it — we don't launch a browser here, since there'd be nothing to fill."""
        with self._lock:
            host = self._host if (self._host and self._host.is_alive()) else None
            if host is None or host._context is None:
                return {"requested": False,
                        "detail": "Open the integrated browser and a few job tabs first "
                                  "(use ⚡ on any job), then try again."}
            host.request_apply_all()
        return {"requested": True}

    def all_statuses(self) -> list[dict]:
        if not self._host:
            return []
        out = []
        for app_id, s in list(self._host.sessions.items()):
            st = s.status()
            st.update({"application_id": app_id, "url": s.job_url, "adopted": s.adopted})
            out.append(st)
        return out
