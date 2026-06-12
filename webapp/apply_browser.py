"""Integrated application browser.

"Apply" in the UI opens the posting in a headed Chromium window driven by
Playwright (already a project dependency). The window uses a persistent
profile under data/browser_profile/ so ATS logins and autofill survive across
sessions, and every navigation is watched: when a page looks like a
submission confirmation, the application is marked applied automatically
(with the confirming URL recorded in application_events). If the user closes
the window without a detected confirmation, the application stays
in_progress for one-click manual resolution in the UI.

Sessions run in daemon threads (Playwright sync API can't share the server's
event loop); state is communicated through the database plus a small
in-memory registry the UI polls.
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

from . import db

# Heuristics for "your application was submitted" pages. Deliberately
# conservative: a false 'applied' is worse than asking the user to confirm.
CONFIRM_URL = re.compile(r"(confirmation|thank[-_]?you|application[-_/]?(submitted|complete|received))", re.I)
CONFIRM_TEXT = re.compile(
    r"(application (has been |was )?(submitted|received|complete)"
    r"|thank you for (applying|your application)"
    r"|we('ve| have) received your application)",
    re.I,
)


def looks_like_confirmation(url: str, title: str = "", body_text: str = "") -> bool:
    if CONFIRM_URL.search(url or ""):
        return True
    return bool(CONFIRM_TEXT.search(f"{title}\n{body_text or ''}"[:20000]))


class ApplySession:
    def __init__(self, application_id: int, job_url: str, db_path: Path, profile_dir: Path):
        self.application_id = application_id
        self.job_url = job_url
        self.db_path = db_path
        self.profile_dir = profile_dir
        self.state = "starting"      # starting | open | applied | closed | error
        self.detail = ""
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # Runs in its own thread with its own DB connection (sqlite is per-thread).
    def _run(self) -> None:
        conn = db.connect(self.db_path)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.state, self.detail = "error", "playwright not installed — pip install playwright && playwright install chromium"
            return
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=False,
                    viewport=None,
                    args=["--start-maximized"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                confirmed = threading.Event()

                def check(frame_page) -> None:
                    if confirmed.is_set():
                        return
                    try:
                        url, title = frame_page.url, frame_page.title()
                        body = ""
                        if CONFIRM_URL.search(url) is None:
                            body = frame_page.inner_text("body", timeout=2000)[:20000]
                        if looks_like_confirmation(url, title, body):
                            confirmed.set()
                            self.state, self.detail = "applied", url
                            db.set_application_status(
                                conn, self.application_id, "applied",
                                detail=f"confirmation detected at {url}",
                                via="integrated_browser",
                            )
                    except Exception:  # noqa: BLE001 — detection is best-effort
                        pass

                page.on("load", check)
                context.on("page", lambda new_page: new_page.on("load", check))

                db.set_application_status(conn, self.application_id, "in_progress",
                                          detail=f"opened {self.job_url}", via="integrated_browser")
                self.state = "open"
                page.goto(self.job_url, wait_until="domcontentloaded")
                context.wait_for_event("close", timeout=0)  # until the user closes the window
        except Exception as exc:  # window closed / browser quit ends up here too
            if self.state == "open":
                self.state = "closed" if not isinstance(exc, ImportError) else "error"
                if self.state == "closed":
                    self.detail = "window closed without a detected confirmation"
                else:
                    self.detail = str(exc)
        finally:
            if self.state == "open":
                self.state = "closed"
                self.detail = "window closed without a detected confirmation"
            conn.close()
            print(f"apply session {self.application_id}: {self.state}", file=sys.stderr)


class SessionRegistry:
    """One live session per application; the UI polls /api/apply-status."""

    def __init__(self, db_path: Path, profile_dir: Path):
        self.db_path = db_path
        self.profile_dir = profile_dir
        self._sessions: dict[int, ApplySession] = {}
        self._lock = threading.Lock()

    def launch(self, application_id: int, job_url: str) -> ApplySession:
        with self._lock:
            existing = self._sessions.get(application_id)
            if existing and existing.state in ("starting", "open"):
                return existing
            session = ApplySession(application_id, job_url, self.db_path, self.profile_dir)
            self._sessions[application_id] = session
            session.start()
            return session

    def status(self, application_id: int) -> dict:
        session = self._sessions.get(application_id)
        if not session:
            return {"state": "none", "detail": ""}
        return {"state": session.state, "detail": session.detail}
