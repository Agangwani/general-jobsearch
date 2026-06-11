"""Shared headless-Chromium runtime for boards without a public API.

One browser instance is shared by all browser fetchers (they run sequentially
after the API pass). The primary extraction technique is XHR capture: navigate
the career page and collect the JSON responses its own frontend loads, which
survives markup redesigns far better than CSS selectors.

Playwright is an optional dependency — if it (or the Chromium binary) is
missing, BrowserUnavailable is raised and the pipeline reports an actionable
error for browser-backed companies instead of failing the run.
"""

from __future__ import annotations

import re

from .http import USER_AGENT


class BrowserUnavailable(RuntimeError):
    pass


_INSTALL_HINT = "pip install playwright && playwright install chromium"


class BrowserRuntime:
    """Context manager owning one headless Chromium for the whole run."""

    def __init__(self, timeout_seconds: int = 45):
        self.timeout_ms = timeout_seconds * 1000
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(f"playwright not installed — {_INSTALL_HINT}") from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:
            self._pw.stop()
            raise BrowserUnavailable(f"chromium launch failed ({exc}) — {_INSTALL_HINT}") from exc
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        self._context.set_default_timeout(self.timeout_ms)

    def __enter__(self) -> "BrowserRuntime":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        for closer in (self._context.close, self._browser.close, self._pw.stop):
            try:
                closer()
            except Exception:
                pass

    def capture_json(self, url: str, url_pattern: str, settle_ms: int = 8000) -> list:
        """Navigate `url` and return the JSON bodies of all responses whose
        request URL matches `url_pattern` (regex)."""
        pattern = re.compile(url_pattern)
        page = self._context.new_page()
        matched = []
        page.on("response", lambda resp: matched.append(resp) if pattern.search(resp.url) else None)
        try:
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=settle_ms)
            except Exception:
                pass  # busy pages never go idle; whatever was captured is enough
            payloads = []
            for resp in matched:
                try:
                    payloads.append(resp.json())
                except Exception:
                    continue  # non-JSON or disposed body
            return payloads
        finally:
            page.close()

    def extract_links(self, url: str, selector: str, wait_selector: str | None = None) -> list[dict]:
        """Navigate `url` and return [{text, href}] for every `selector` match —
        the DOM fallback for fully static listings."""
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(wait_selector or selector, timeout=self.timeout_ms)
            except Exception:
                pass
            return page.eval_on_selector_all(
                selector,
                "els => els.map(el => ({text: el.innerText, href: el.href || ''}))",
            )
        finally:
            page.close()
