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

import json
import re

from .http import USER_AGENT


class BrowserUnavailable(RuntimeError):
    pass


_INSTALL_HINT = "pip install playwright && playwright install chromium"

# Cookie-consent walls (OneTrust/TrustArc/...) on bank career sites block the
# jobs XHR until dismissed — try these before judging a page empty.
_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#truste-consent-button",
    "button[id*='accept-recommended']",
    "button[data-testid*='accept']",
)

# JSON hiding in the final DOM: SPA state globals (Next.js, Redux, and
# window.phApp.ddo — the Phenom platform behind careers.jpmorgan.com and
# mlp.com embeds its first page of search results there) plus JSON script
# tags, including schema.org JobPosting JSON-LD that career sites embed for
# Google-for-Jobs SEO.
_EMBEDDED_JS = """
() => {
  const out = [];
  const push = v => { try { const s = JSON.stringify(v); if (s && s.length > 2) out.push(s); } catch (e) {} };
  for (const k of ['__NEXT_DATA__', '__INITIAL_STATE__', '__APP_INITIAL_STATE__',
                   '__PRELOADED_STATE__', '__REDUX_STATE__'])
    if (window[k]) push(window[k]);
  if (window.phApp && window.phApp.ddo) push(window.phApp.ddo);
  for (const s of document.querySelectorAll(
        'script[type="application/json"], script[type="application/ld+json"]'))
    if (s.textContent && s.textContent.length < 2000000) out.push(s.textContent);
  return out;
}
"""


def parse_embedded(raw_blobs: list[str]) -> list:
    """JSON-decode the strings harvested from the DOM, dropping anything that
    isn't valid JSON. Pure — offline-tested."""
    parsed = []
    for blob in raw_blobs or []:
        try:
            value = json.loads(blob)
        except (TypeError, ValueError):
            continue
        if isinstance(value, (dict, list)) and value:
            parsed.append(value)
    return parsed


# XSSI guards some APIs prefix to JSON bodies (Google uses )]}' ) — these
# make Response.json() fail, silently dropping the payload.
_XSSI_GUARDS = (")]}'", "&&&START&&&", "while(1);", "for(;;);")
_ASSET_RE = re.compile(r"\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|mp4|webp)(\?|$)", re.I)


def parse_json_text(text: str):
    """JSON-decode a response body, tolerating XSSI guard prefixes. Returns
    None when the body isn't JSON. Pure — offline-tested."""
    if not text:
        return None
    stripped = text.lstrip()
    for guard in _XSSI_GUARDS:
        if stripped.startswith(guard):
            stripped = stripped[len(guard):].lstrip()
            break
    try:
        value = json.loads(stripped)
    except ValueError:
        return None
    return value if isinstance(value, (dict, list)) else None


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
            self._browser = self._pw.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"])
        except Exception as exc:
            self._pw.stop()
            raise BrowserUnavailable(f"chromium launch failed ({exc}) — {_INSTALL_HINT}") from exc
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        # Plain headless Chromium advertises itself via navigator.webdriver,
        # which several career sites use to serve an empty shell.
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
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
        return self.harvest(url, url_pattern, settle_ms)["matched"]

    def harvest(self, url: str, url_pattern: str, settle_ms: int = 8000,
                attempts: int = 2) -> dict:
        """Navigate `url` and bring back every place job data could hide:

        - "matched":  JSON bodies of responses whose URL matches `url_pattern`
        - "extra":    every other JSON response the page loaded (any domain —
                      frontends often call a vendor API the pattern missed)
        - "embedded": JSON dug out of the final DOM (SPA state globals,
                      Phenom's phApp.ddo, JSON-LD script tags)

        Dismisses cookie-consent walls, scrolls to trigger lazy lists, and
        retries once with a longer settle when nothing job-shaped came back —
        flaky boards (Millennium) usually land on the second pass."""
        pattern = re.compile(url_pattern)
        result = {"matched": [], "extra": [], "embedded": []}
        for attempt in range(attempts):
            result = self._harvest_once(url, pattern, settle_ms * (attempt + 1))
            if result["matched"] or result["embedded"]:
                break
        return result

    def _harvest_once(self, url: str, pattern: re.Pattern, settle_ms: int) -> dict:
        page = self._context.new_page()
        responses = []
        page.on("response", lambda resp: responses.append(resp))
        try:
            page.goto(url, wait_until="domcontentloaded")
            self._dismiss_consent(page)
            self._scroll(page)
            try:
                page.wait_for_load_state("networkidle", timeout=settle_ms)
            except Exception:
                pass  # busy pages never go idle; whatever was captured is enough

            matched, extra, seen_urls = [], [], []
            for resp in responses:
                if not _ASSET_RE.search(resp.url):
                    seen_urls.append(resp.url)
                is_match = bool(pattern.search(resp.url))
                if not is_match and "json" not in resp.headers.get("content-type", ""):
                    continue  # only pattern hits get the benefit of the doubt
                try:
                    payload = resp.json()
                except Exception:
                    try:
                        payload = parse_json_text(resp.text())  # XSSI-guarded body?
                    except Exception:
                        payload = None  # disposed body
                if payload is None:
                    continue
                (matched if is_match else extra).append(payload)

            try:
                embedded = parse_embedded(page.evaluate(_EMBEDDED_JS))
            except Exception:
                embedded = []
            return {"matched": matched, "extra": extra, "embedded": embedded,
                    "debug": {"final_url": page.url, "response_urls": seen_urls[:40]}}
        finally:
            page.close()

    def _dismiss_consent(self, page) -> None:
        for selector in _CONSENT_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=400):
                    button.click(timeout=1000)
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    def _scroll(self, page, passes: int = 3) -> None:
        for _ in range(passes):
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(500)
            except Exception:
                return

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
