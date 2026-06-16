"""ATS (applicant-tracking-system) awareness for the apply browser.

The apply engine is deliberately generic — it reads whatever form a page
renders and matches controls to the profile. But three things vary so much
between ATS platforms that the generic engine alone gets them wrong, and this
module supplies the platform-specific knowledge to fix them:

1. ``canonical_apply_url`` — rewrite a posting/branded URL to the page that
   actually renders the application FORM. A Greenhouse link can point at a
   company-branded posting page that embeds the real form in a *cross-origin*
   iframe (unreadable), or at a posting page gated behind an "Apply" button.
   Landing directly on ``/embed/job_app`` (Greenhouse), ``/application``
   (Ashby) or ``/apply`` (Lever) skips both problems.

2. ``is_cloudflare_challenge`` / ``ats_form_iframe_src`` — runtime checks the
   BrowserHost runs on the live (sync) Playwright page: is this a Cloudflare
   interstitial we must wait out, and is the real form sitting in an ATS
   iframe we should hoist to the top level?

3. ``greenhouse_questions`` — Greenhouse publishes the exact application
   schema (field names, types, required flags, and the *exact* option labels
   for every dropdown). Driving the fill from that schema is far more accurate
   than guessing from the DOM, especially for custom ``question_NNNN`` selects.

Everything degrades gracefully: detection failures, network errors, and
unknown platforms all fall back to the generic DOM-driven engine.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse, urlunparse

GREENHOUSE = "greenhouse"
ASHBY = "ashby"
LEVER = "lever"
WORKDAY = "workday"
EIGHTFOLD = "eightfold"
CUSTOM = "custom"


# --------------------------------------------------------------- detection
def detect_platform(url: str) -> str:
    """Best-effort ATS identification from a posting/apply URL."""
    if not url:
        return CUSTOM
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    query = parsed.query.lower()
    if host.endswith("greenhouse.io") or "gh_jid=" in query:
        return GREENHOUSE
    if host.endswith("ashbyhq.com") or host.endswith("careerpuck.com"):
        return ASHBY
    if host.endswith("lever.co"):
        return LEVER
    if "myworkdayjobs.com" in host or re.search(r"\.wd\d+\.", host):
        return WORKDAY
    if host.endswith("eightfold.ai"):
        return EIGHTFOLD
    return CUSTOM


# ----------------------------------------------------------- greenhouse url
def parse_greenhouse(url: str) -> tuple[str, str, str] | None:
    """Extract ``(board, job_id, host)`` from any Greenhouse URL form.

    Handles both URL dialects, which (maddeningly) swap the meaning of the
    ``token`` query param:
      - new:    job-boards.greenhouse.io/embed/job_app?for=<board>&token=<id>
      - legacy: boards.greenhouse.io/embed/job_app?token=<board>&gh_jid=<id>
      - hosted: (job-)boards.greenhouse.io/<board>/jobs/<id>
    Returns ``None`` when the board can't be determined (e.g. a company-branded
    URL that only carries ``gh_jid`` — those are handled at runtime by hoisting
    the embed iframe instead).
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    qs = parse_qs(parsed.query)
    parts = [p for p in parsed.path.split("/") if p]

    def first(*keys: str) -> str:
        for key in keys:
            if qs.get(key):
                return qs[key][0]
        return ""

    if "embed" in parts or "job_app" in parts:
        if qs.get("for"):  # new dialect
            board, job_id = first("for"), first("token", "gh_jid")
        else:              # legacy dialect: token holds the board
            board, job_id = first("token"), first("gh_jid")
        return (board, job_id, host) if board and job_id else None

    if "jobs" in parts:
        i = parts.index("jobs")
        if i >= 1 and i + 1 < len(parts):
            return (parts[i - 1], parts[i + 1], host)

    return None


def _greenhouse_embed_url(board: str, job_id: str, host: str) -> str:
    # Rebuild the bare embedded form on the same host family the link used, so
    # we never migrate a still-legacy board onto a host that 404s it.
    if host == "boards.greenhouse.io":
        return f"https://boards.greenhouse.io/embed/job_app?token={board}&gh_jid={job_id}"
    return f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={job_id}"


def _ensure_path_suffix(url: str, suffix: str, min_segments: int) -> str:
    """Append ``/<suffix>`` to a URL's path unless it's already there."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if suffix in parts or len(parts) < min_segments:
        return url
    new_path = "/" + "/".join(parts + [suffix])
    return urlunparse(parsed._replace(path=new_path))


def canonical_apply_url(url: str) -> str:
    """Rewrite a posting URL to the page that renders the application form.

    Conservative: only rewrites when the platform and IDs are unambiguous;
    anything else is returned untouched and handled at runtime.
    """
    platform = detect_platform(url)
    if platform == GREENHOUSE:
        parsed = parse_greenhouse(url)
        if parsed:
            return _greenhouse_embed_url(*parsed)
        return url
    if platform == ASHBY:
        return _ensure_path_suffix(url, "application", min_segments=2)
    if platform == LEVER:
        return _ensure_path_suffix(url, "apply", min_segments=2)
    return url


# ----------------------------------------------------- runtime page helpers
_CF_TITLE = re.compile(
    r"just a moment|attention required|checking your browser|verify you are human",
    re.I,
)
_CF_SELECTORS = (
    'iframe[src*="challenges.cloudflare.com"]',
    'script[src*="challenge-platform"]',
    "#challenge-running",
    "#cf-challenge-running",
    "form#challenge-form",
)
_ATS_IFRAME = re.compile(
    r"(greenhouse\.io|ashbyhq\.com|lever\.co|myworkdayjobs\.com)/", re.I
)


def is_cloudflare_challenge(page) -> bool:
    """True when the live page is a Cloudflare interstitial (sync Playwright).

    Cheap on purpose — title + a few marker selectors, no full ``content()`` —
    because the BrowserHost calls it on every settle.
    """
    try:
        if _CF_TITLE.search(page.title() or ""):
            return True
    except Exception:  # noqa: BLE001 — page may be mid-navigation
        return False
    for selector in _CF_SELECTORS:
        try:
            if page.locator(selector).count():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def ats_form_iframe_src(page) -> str | None:
    """If the real application form is in a cross-origin ATS iframe, return its
    URL so the caller can navigate the tab to it (turning the form top-level
    and therefore readable). ``page.frames`` exposes cross-origin frame URLs
    even when their DOM is unreadable."""
    try:
        frames = page.frames
    except Exception:  # noqa: BLE001
        return None
    page_url = getattr(page, "url", "")
    for frame in frames:
        src = getattr(frame, "url", "") or ""
        if src and src != page_url and _ATS_IFRAME.search(src):
            return src
    return None


# --------------------------------------------------------- greenhouse schema
# Greenhouse renders each field as <input name="job_application[<field>]">.
_GH_FIELD_NAME = re.compile(r"^job_application\[([a-zA-Z0-9_]+)\]$")
_GH_SELECT_TYPES = {"multi_value_single_select", "multi_value_multi_select"}


def parse_greenhouse_payload(data: dict) -> dict[str, dict]:
    """Flatten a Greenhouse ``?questions=true`` payload to ``{field_name:
    {label, required, type, options}}``. Pure — unit-tested without network."""
    schema: dict[str, dict] = {}
    for question in data.get("questions", []) or []:
        label = question.get("label", "") or ""
        required = bool(question.get("required"))
        for field in question.get("fields", []) or []:
            name = field.get("name")
            if not name:
                continue
            options = [
                {"value": str(v.get("value", "")), "text": str(v.get("label", ""))}
                for v in (field.get("values") or [])
            ]
            schema[name] = {
                "label": label,
                "required": required,
                "type": field.get("type", ""),
                "options": options,
            }
    return schema


def greenhouse_questions(board: str, job_id: str, *, timeout: float = 8.0):
    """Fetch the public Greenhouse application schema. Returns the flattened
    ``{field_name: spec}`` dict, or ``None`` on any failure."""
    if not (board and job_id):
        return None
    url = (
        f"https://boards-api.greenhouse.io/v1/boards/{board}"
        f"/jobs/{job_id}?questions=true"
    )
    try:
        import requests

        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_greenhouse_payload(resp.json()) or None
    except Exception:  # noqa: BLE001 — network/JSON/HTTP all degrade to DOM
        return None


def greenhouse_schema_for(url: str):
    """Convenience: parse a Greenhouse URL and fetch its schema in one step."""
    parsed = parse_greenhouse(url)
    if not parsed:
        return None
    board, job_id, _ = parsed
    return greenhouse_questions(board, job_id)


# Map a DOM control's name attribute to its Greenhouse schema field name.
def greenhouse_field_name(dom_name: str) -> str:
    match = _GH_FIELD_NAME.match(dom_name or "")
    return match.group(1) if match else ""


def is_greenhouse_select_type(field_type: str) -> bool:
    return field_type in _GH_SELECT_TYPES


def greenhouse_job_id(url: str) -> str:
    """The Greenhouse job id from any URL form — the embed/hosted form, or a
    company-branded posting carrying ``?gh_jid=``. Used to match an open tab
    back to a stored (often branded) job URL. Empty string if not Greenhouse."""
    parsed = parse_greenhouse(url)
    if parsed:
        return parsed[1]
    match = re.search(r"[?&]gh_jid=(\d+)", url or "")
    return match.group(1) if match else ""
