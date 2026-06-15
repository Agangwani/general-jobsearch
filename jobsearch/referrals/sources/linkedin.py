"""LinkedIn People Search via Playwright.

Why headed + persistent context: LinkedIn aggressively detects automation.
A persistent user-data-dir at data/browser_profile/linkedin/ lets the user
log in once manually and reuses that session forever. Headed mode means the
user can solve any verification challenge LinkedIn throws (CAPTCHA, "is this
you?", phone verification). We never log in programmatically — that path
gets accounts banned.

Threading model: Playwright's sync API binds every object to the thread that
created it (greenlet event loop) — calling _context.new_page() from a thread
other than the one that started sync_playwright() raises or hangs. FastAPI
fires each search in a fresh worker thread, so we pin all Playwright work to
a single dedicated ThreadPoolExecutor(max_workers=1) worker. `search()` from
any thread submits onto that worker and blocks for the result; the worker
keeps Playwright alive across requests so the Chromium window stays open.

Page reuse: we keep one `_main_page` and navigate it in place across
searches. That serves two purposes — it gives LoginRequired a stable surface
(the page stays at LinkedIn's login URL so the user can sign in there), and
it avoids opening orphan tabs that would close the persistent context's only
window the moment we cleaned them up. Closing the only tab of a persistent
context's headed window terminates the window, which was the original
"window auto-closes before I can log in" bug.

Parsing strategy: rather than depend on a specific React class name (which
LinkedIn rewrites every few months), we anchor on `a[href*="/in/"]` profile
links and walk the surrounding card for name + headline + location. Robust
to most DOM rewrites; degrades gracefully when LinkedIn ships a redesign.
"""

from __future__ import annotations

import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

# A typical search result anchors on a profile link; the surrounding card
# carries everything else we need (name, headline, current role hint).
_SLUG_RE = re.compile(r"/in/([^/?#]+)/?")
_RESULT_WAIT_MS = 8000
_SCROLL_PAUSE_MS = 1200


@dataclass
class CandidateHit:
    """A single search-result row. Sparse on purpose — P1 only reads the
    search results page; profile-visit enrichment is a P2/P3 addition."""

    name: str
    headline: str = ""
    current_role: str = ""
    current_company: str = ""
    location: str = ""
    linkedin_url: str = ""
    raw_text: str = ""

    def document(self) -> str:
        """The text we score against the job description and the resume."""
        return " ".join(filter(None, [
            self.name, self.headline, self.current_role,
            self.current_company, self.location, self.raw_text,
        ]))


class LoginRequired(RuntimeError):
    """Raised when LinkedIn shows a login/auth wall instead of results.
    The webapp catches this and surfaces a 'log in to LinkedIn in the browser
    window that just opened, then retry' message."""


class LinkedinDiscoverer:
    """Persistent Chromium for LinkedIn discovery, owned by a dedicated worker.

    All Playwright work runs on a single ThreadPoolExecutor worker — required
    because the sync API is thread-bound. `search()` is thread-safe: it
    submits to the worker and blocks for the result. The browser window stays
    open across searches; one `_main_page` is reused (navigated in place).
    """

    def __init__(
        self,
        profile_dir: Path,
        *,
        headless: bool = False,
        max_candidates: int = 25,
        between_searches_min_s: float = 3.0,
        between_searches_max_s: float = 7.0,
    ):
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.max_candidates = max_candidates
        self.between_searches_min_s = between_searches_min_s
        self.between_searches_max_s = between_searches_max_s
        # max_workers=1 → every Playwright call happens on the same thread;
        # FastAPI worker threads submit jobs and block on the future.
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="linkedin-discovery")
        self._pw = None
        self._context = None
        self._main_page = None
        self._last_search_at = 0.0

    # ------------------------------------------------------------- public ---

    def search(self, company: str, role_query: str = "") -> list[CandidateHit]:
        """Search LinkedIn for current employees at `company` whose profile
        text matches `role_query`. Re-raises LoginRequired so the caller can
        surface a 'log in to LinkedIn in the open window, then retry' message
        without closing the window — the next search will reuse the
        now-logged-in page."""
        return self._executor.submit(
            self._search_in_worker, company, role_query).result()

    def close(self) -> None:
        """Tear down Playwright and the worker. Best-effort: if a search is
        in flight beyond the timeout we drop into a non-blocking shutdown and
        let the OS reap the browser when the process exits."""
        try:
            self._executor.submit(self._teardown_in_worker).result(timeout=5)
        except Exception:  # noqa: BLE001 — already torn down, or stuck
            pass
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------- worker ---
    # Everything below runs on the dedicated worker thread.

    def _search_in_worker(self, company: str, role_query: str) -> list[CandidateHit]:
        ctx = self._ensure_context()
        page = self._ensure_main_page(ctx)
        self._respect_rate_limit()
        try:
            return self._search_on_page(page, company, role_query)
        finally:
            self._last_search_at = time.monotonic()

    def _ensure_context(self):
        # Recreate if a previous context died (user closed the whole window).
        if self._context is not None:
            try:
                _ = self._context.pages
            except Exception:  # noqa: BLE001
                self._context = None
                self._main_page = None
        if self._context is not None:
            return self._context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright not installed — pip install playwright "
                "&& playwright install chromium"
            ) from exc
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if self._pw is None:
            self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport=None,
            args=["--start-maximized"],
        )
        return self._context

    def _ensure_main_page(self, ctx):
        """Reuse the same tab across searches. If the user closed it we open
        a new one. Reusing matters: navigating in place keeps any login wall
        visible long enough for the user to sign in, and avoids closing the
        only tab of a persistent context (which would kill the window)."""
        if self._main_page is not None:
            try:
                if not self._main_page.is_closed():
                    return self._main_page
            except Exception:  # noqa: BLE001
                pass
        # Prefer reusing the launch-time blank tab so we never end up with
        # two tabs after the first call.
        try:
            pages = ctx.pages
        except Exception:  # noqa: BLE001
            pages = []
        if pages and (pages[0].url == "about:blank" or pages[0].url == ""):
            self._main_page = pages[0]
        else:
            self._main_page = ctx.new_page()
        return self._main_page

    def _teardown_in_worker(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:  # noqa: BLE001
                pass
            self._context = None
            self._main_page = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_search_at
        wait = random.uniform(self.between_searches_min_s, self.between_searches_max_s) - elapsed
        if wait > 0:
            time.sleep(wait)

    def _search_on_page(self, page, company: str, role_query: str) -> list[CandidateHit]:
        # Quote the company to bias LinkedIn toward people who currently work
        # there rather than have it as a substring elsewhere in their profile.
        keywords = f'"{company}"'
        if role_query:
            keywords += f" {role_query}"
        url = (
            "https://www.linkedin.com/search/results/people/?"
            f"keywords={quote_plus(keywords)}&origin=GLOBAL_SEARCH_HEADER"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if _looks_like_login_wall(page):
            raise LoginRequired(
                "LinkedIn is showing a login wall. Log in to your LinkedIn "
                "account in the Chromium window that opened, then re-run the "
                "search. Your session is saved across runs."
            )

        # Search results take a beat to hydrate on first navigation.
        try:
            page.wait_for_selector("a[href*='/in/']", timeout=_RESULT_WAIT_MS)
        except Exception:  # noqa: BLE001 — empty results or DOM didn't load
            return []

        # One scroll loads the second page of results without triggering
        # LinkedIn's "show more results" capture.
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(_SCROLL_PAUSE_MS)
        except Exception:  # noqa: BLE001
            pass

        return _parse_results(page, company, self.max_candidates)


# ------------------------------------------------------------------- parse ---

_LOGIN_HINTS = ("authwall", "login", "checkpoint", "uas/login")


def _looks_like_login_wall(page) -> bool:
    url = (page.url or "").lower()
    if any(hint in url for hint in _LOGIN_HINTS):
        return True
    # On the public auth wall, LinkedIn shows a prominent "Sign in" form.
    try:
        if page.locator("input[name='session_key']").count() > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _parse_results(page, target_company: str, limit: int) -> list[CandidateHit]:
    """Walk profile-link anchors and harvest the surrounding card. We dedupe
    on the canonical /in/<slug>/ URL because LinkedIn often duplicates the
    same person across name, image, and headline anchors within a card."""
    hits: list[CandidateHit] = []
    seen_slugs: set[str] = set()
    target_lc = target_company.lower().strip()

    try:
        anchors = page.locator("a[href*='/in/']").all()
    except Exception:  # noqa: BLE001
        return hits

    for anchor in anchors:
        if len(hits) >= limit:
            break
        try:
            href = anchor.get_attribute("href") or ""
        except Exception:  # noqa: BLE001
            continue
        match = _SLUG_RE.search(href)
        if not match:
            continue
        slug = match.group(1)
        if slug in seen_slugs or slug in ("public-profile",):
            continue
        seen_slugs.add(slug)

        card_text = _enclosing_card_text(anchor)
        name = _first_nonempty_line(card_text) or _safe_inner_text(anchor)
        if not name:
            continue
        headline = _line_after(card_text, name)
        location = _last_short_line(card_text)
        current_role, current_company = _split_role_company(headline)

        # Cheap relevance gate: drop rows whose card never mentions the
        # target company. This catches LinkedIn surfacing past-employees
        # whose current company is different.
        if target_lc and target_lc not in card_text.lower():
            continue

        hits.append(CandidateHit(
            name=name.strip(),
            headline=headline.strip(),
            current_role=current_role,
            current_company=current_company or target_company,
            location=location.strip(),
            linkedin_url=f"https://www.linkedin.com/in/{slug}/",
            raw_text=card_text[:2000],
        ))
    return hits


def _enclosing_card_text(anchor) -> str:
    """Walk up the DOM to find the result card that contains this anchor and
    return its text. <li> is LinkedIn's stable card wrapper; the entity-result
    div is a fallback for layouts that use a flat list."""
    for selector in ("xpath=ancestor::li[1]", "xpath=ancestor::div[contains(@class,'entity-result')][1]"):
        try:
            ancestor = anchor.locator(selector).first
            if ancestor.count() == 0:
                continue
            text = ancestor.inner_text(timeout=1500)
            if text:
                return text
        except Exception:  # noqa: BLE001
            continue
    return _safe_inner_text(anchor)


def _safe_inner_text(loc) -> str:
    try:
        return loc.inner_text(timeout=1500) or ""
    except Exception:  # noqa: BLE001
        return ""


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("•") and "Status is" not in line:
            return line
    return ""


def _line_after(text: str, marker: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        idx = lines.index(marker.strip())
    except ValueError:
        return lines[1] if len(lines) > 1 else ""
    return lines[idx + 1] if idx + 1 < len(lines) else ""


def _last_short_line(text: str) -> str:
    """Location is usually the last short line on a LinkedIn card (under 60
    chars). Skips connection-degree pills and 'View profile' hints."""
    candidates = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and len(ln.strip()) <= 60
        and not ln.strip().endswith("connection")
        and "View " not in ln
    ]
    return candidates[-1] if candidates else ""


def _split_role_company(headline: str) -> tuple[str, str]:
    """LinkedIn headlines often read 'Senior SWE at OpenAI' or
    'Senior SWE @ OpenAI | python, k8s'. Extract role + company best-effort;
    fall back to the whole headline as role and empty company."""
    if not headline:
        return "", ""
    for sep in (" at ", " @ "):
        if sep in headline:
            left, right = headline.split(sep, 1)
            company = right.split("|")[0].split("•")[0].split("·")[0].strip()
            return left.strip(), company
    return headline.strip(), ""
