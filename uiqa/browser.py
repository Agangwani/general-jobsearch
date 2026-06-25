"""A real headless Chromium the agents drive, with everything-that-could-be-a-bug
capture wired in.

We listen on the whole browser *context*, not just the first page, so the
apply-browser pop-ups and any window.open()'d sub-windows the user mentioned are
captured too. Every console error/warning, uncaught JS exception, failed
request, and 4xx/5xx response is appended to a single ordered event log that the
scenario runner drains per step.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .appserver import _default_browsers_path

# Severity tiers so the explorer/validator can triage without reparsing text.
SEVERITY = {
    "page_error": "high",        # uncaught JS exception — almost always a real bug
    "http_error_5xx": "high",    # server blew up
    "http_error_4xx": "medium",  # often a real broken link/missing route
    "request_failed": "medium",
    "console_error": "medium",
    "console_warning": "low",
}
# Network kinds whose severity drops to "low" when the resource is off-origin —
# a blocked third-party font/CDN is the environment, not a bug in *this* app.
_NETWORK_KINDS = {"http_error_4xx", "http_error_5xx", "request_failed"}


@dataclass
class BrowserEvent:
    kind: str
    text: str
    url: str = ""
    page_url: str = ""
    external: bool = False
    ts: float = field(default_factory=time.time)

    @property
    def severity(self) -> str:
        # Off-origin resource failures (blocked fonts/CDNs) are environmental.
        if self.external and self.kind in _NETWORK_KINDS:
            return "low"
        # The console "Failed to load resource" line always mirrors a network
        # event we already classified; don't double-count it as a medium error.
        if self.kind == "console_error" and self.text.startswith("Failed to load resource"):
            return "low"
        return SEVERITY.get(self.kind, "low")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "text": self.text,
                "url": self.url, "page_url": self.page_url, "external": self.external}


class BrowserSession:
    """Wraps a Playwright page with capture + a small, agent-friendly action API.
    Use as a context manager."""

    def __init__(self, *, headless: bool = True, base_url: str = ""):
        self.headless = headless
        self.base_url = base_url.rstrip("/")
        self._origin = _origin_of(self.base_url)
        self.events: list[BrowserEvent] = []
        self._cursor = 0
        self._pw = None
        self._browser = None
        self.context = None
        self.page = None
        self.popups: list[Any] = []

    # ---------------------------------------------------------------- lifecycle
    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        bp = _default_browsers_path()
        if bp:
            import os
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bp))
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self.context = self._browser.new_context()
        self.context.on("page", self._wire_page)  # pop-ups / new windows
        self.page = self.context.new_page()
        self._wire_page(self.page)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass

    # ----------------------------------------------------------------- capture
    def _wire_page(self, page) -> None:
        # The context fires this for every page including pop-ups / new windows
        # (apply-browser tabs, target=_blank). The first call is the main page.
        if self.page is not None and page is not self.page:
            self.popups.append(page)

        def on_console(msg):
            t = msg.type
            if t in ("error", "warning"):
                self._add("console_error" if t == "error" else "console_warning",
                          msg.text, page_url=_safe_url(page))

        def on_pageerror(err):
            self._add("page_error", str(err), page_url=_safe_url(page))

        def on_requestfailed(req):
            # Ignore intentional aborts; report genuine network failures.
            failure = getattr(req, "failure", None)
            txt = failure if isinstance(failure, str) else (failure or "")
            self._add("request_failed", f"{req.method} {req.url} — {txt}",
                      url=req.url, page_url=_safe_url(page))

        def on_response(resp):
            if resp.status >= 400:
                kind = "http_error_5xx" if resp.status >= 500 else "http_error_4xx"
                self._add(kind, f"{resp.status} {resp.url}", url=resp.url,
                          page_url=_safe_url(page))

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("requestfailed", on_requestfailed)
        page.on("response", on_response)

    def _add(self, kind: str, text: str, *, url: str = "", page_url: str = "") -> None:
        external = bool(url) and _origin_of(url) != self._origin
        self.events.append(BrowserEvent(kind=kind, text=text[:1000], url=url,
                                        page_url=page_url, external=external))

    def drain(self) -> list[BrowserEvent]:
        """Events captured since the last drain — lets the runner attribute
        them to one step."""
        out = self.events[self._cursor:]
        self._cursor = len(self.events)
        # Let microtask-queued console errors land before the caller reads them.
        return out

    def settle(self, ms: int = 250) -> None:
        try:
            self.page.wait_for_timeout(ms)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ actions
    def goto(self, path_or_url: str, *, timeout: int = 15000) -> int:
        url = path_or_url if path_or_url.startswith("http") else self.base_url + path_or_url
        resp = self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        self.settle()
        return resp.status if resp else 0

    def click(self, *, selector: str = "", text: str = "", timeout: int = 8000) -> None:
        loc = self.page.locator(selector) if selector else \
            self.page.get_by_text(text, exact=False).first
        loc.click(timeout=timeout)
        self.settle()

    def fill(self, selector: str, value: str, *, timeout: int = 8000) -> None:
        self.page.fill(selector, value, timeout=timeout)

    def select_option(self, selector: str, value: str, *, timeout: int = 8000) -> None:
        self.page.select_option(selector, value, timeout=timeout)
        self.settle()

    def set_checked(self, selector: str, checked: bool, *, timeout: int = 8000) -> None:
        self.page.set_checked(selector, checked, timeout=timeout)

    def upload(self, selector: str, file_path: str, *, timeout: int = 8000) -> None:
        self.page.set_input_files(selector, file_path, timeout=timeout)

    def go_back(self) -> None:
        self.page.go_back(wait_until="domcontentloaded")
        self.settle()

    def current_url(self) -> str:
        return _safe_url(self.page)

    def title(self) -> str:
        try:
            return self.page.title()
        except Exception:  # noqa: BLE001
            return ""

    def text(self) -> str:
        try:
            return self.page.inner_text("body")
        except Exception:  # noqa: BLE001
            return ""

    def screenshot(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:  # noqa: BLE001
            return ""


def _safe_url(page) -> str:
    try:
        return page.url
    except Exception:  # noqa: BLE001
        return ""


def _origin_of(url: str) -> str:
    from urllib.parse import urlsplit
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}"
