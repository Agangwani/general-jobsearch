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

from . import autofill, db
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


def looks_like_confirmation(url: str, title: str = "", body_text: str = "") -> bool:
    if CONFIRM_URL.search(url or ""):
        return True
    return bool(CONFIRM_TEXT.search(f"{title}\n{body_text or ''}"[:20000]))


class ApplySession:
    """State holder for one application's tab; driven by the BrowserHost."""

    def __init__(self, application_id: int, job_url: str):
        self.application_id = application_id
        self.job_url = job_url
        self.state = "starting"      # starting | open | applied | closed | error
        self.detail = ""
        self.fill = {"filled": 0, "skipped": 0, "fields": [], "notes": []}
        self.page = None             # owned by the BrowserHost thread
        self.last_url = ""
        self.settled = False
        self.filled_urls: set[str] = set()
        self.clicked_apply = False

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

    def open_tab(self, session: ApplySession) -> None:
        self.sessions[session.application_id] = session
        self._queue.put(session)

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
            context = None
            while True:
                try:
                    session = self._queue.get(timeout=0.5)
                except queue.Empty:
                    session = None
                if session is not None:
                    try:
                        if context is None:
                            context = p.chromium.launch_persistent_context(
                                user_data_dir=str(self.profile_dir),
                                headless=False, viewport=None,
                                args=["--start-maximized"],
                            )
                        session.page = self._fresh_page(context)
                        session.state = "open"
                        db.set_application_status(
                            conn, session.application_id, "in_progress",
                            detail=f"opened {session.job_url}", via="integrated_browser")
                        session.page.goto(session.job_url, wait_until="domcontentloaded")
                    except Exception as exc:  # noqa: BLE001
                        session.state, session.detail = "error", str(exc)[:300]
                        context = self._context_if_alive(context)
                for s in list(self.sessions.values()):
                    if not s.live:
                        continue
                    try:
                        self._tick(s, conn)
                    except Exception:  # noqa: BLE001 — page/context may vanish anytime
                        pass
                if context is not None and not self._context_pages(context):
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001
                        pass
                    context = None

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
        title, body = "", ""
        try:
            title = page.title()
            if not CONFIRM_URL.search(page.url):
                body = page.inner_text("body", timeout=2000)[:20000]
        except Exception:  # noqa: BLE001
            pass
        if s.state != "applied" and looks_like_confirmation(page.url, title, body):
            s.state, s.detail = "applied", page.url
            db.set_application_status(
                conn, s.application_id, "applied",
                detail=f"confirmation detected at {page.url}", via="integrated_browser")
            return
        if s.state == "applied" or page.url in s.filled_urls:
            return
        s.filled_urls.add(page.url)
        try:  # give SPA forms a beat to render
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001
            pass

        prof = {r["field"]: r["value"] for r in profilemod.all_fields(conn)}
        resume = self._resume_path()
        result = autofill.run_fill(page, prof, resume)

        # Posting page rather than a form? Click through to the application
        # form once. If the URL changes, the next tick fills the new page.
        if result["fillable"] < 2 and not s.clicked_apply:
            s.clicked_apply = True
            if autofill.click_apply_button(page):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=4000)
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:  # noqa: BLE001
                    pass
                if page.url == s.last_url:  # form appeared in place
                    result = autofill.run_fill(page, prof, resume)
                else:
                    s.settled = False
                    return

        if result["filled"] or result["skipped"]:
            s.fill["filled"] += result["filled"]
            s.fill["skipped"] += len(result["skipped"])
            s.fill["fields"] += result["fields"]
            s.fill["notes"] = [f"{x['field']}: {x['note']}" for x in result["skipped"]][:30]
        if result["filled"]:
            db.set_application_status(
                conn, s.application_id, "in_progress",
                detail=("auto-filled " + ", ".join(result["fields"][:20])
                        + (f" (+{len(result['skipped'])} left for review)" if result["skipped"] else "")),
                via="autofill")
            print(f"autofill app {s.application_id}: {result['filled']} filled, "
                  f"{len(result['skipped'])} skipped", file=sys.stderr)

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
        pdfs = sorted(self.data_dir.glob("*.pdf"))
        return str(pdfs[-1]) if pdfs else ""


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
