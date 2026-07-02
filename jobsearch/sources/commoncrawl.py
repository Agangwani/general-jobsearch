"""Common Crawl CDX board discovery: mine the open Common Crawl URL index for
public ATS board URLs (Greenhouse / Lever / Ashby) to auto-populate the
`ats_boards` seed — the widest-net way to find companies whose boards exist,
without a hand-curated list.

CDX returns URLs only (no posting text), so these boards can't be ranked on
their own. Instead they SEED the ats_boards source, which fetches each board's
real openings so ranking can score them against the resume — see the ats_boards
module. This keeps a strict split: Common Crawl finds *where the boards are*;
ats_boards + ranking decide *which fit this resume*.

Common Crawl is a public, documented, open dataset (commoncrawl.org). The pure
slug extraction is offline-tested; the network query is best-effort.

Run: ``python -m jobsearch discover-ats-boards`` → writes the discovered board
tokens to ``data/ats_boards.discovered.yaml`` (merged into the ats_boards seed
at discovery time, capped by ``discovery.ats_boards_max``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from ..discover import classify_ats_url

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
# ATS host domains worth crawling for board tokens (host-wildcarded in the query).
ATS_DOMAINS = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
)


def _token_of(detection: dict) -> str:
    """The board/org slug from an ATS detection (the ats_boards seed token)."""
    return detection.get("board") or detection.get("org") or ""


def extract_ats_tokens(lines) -> list[dict]:
    """CDX JSON lines (one object per line) → deduped ``[{ats, token}]`` via the
    shared ATS URL classifier. Non-JSON / non-ATS / token-less lines are skipped.
    Dedup is per (ats, lowercased token)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):   # a valid-JSON scalar/array is not a record
            continue
        det = classify_ats_url(rec.get("url") or "")
        if not det:
            continue
        token = _token_of(det)
        key = (det["ats"], token.lower())
        if not token or key in seen:
            continue
        seen.add(key)
        out.append({"ats": det["ats"], "token": token})
    return out


def _latest_index_url(session) -> str:
    """The newest crawl's CDX API endpoint (collinfo lists newest-first).
    Raises RuntimeError on an empty or unexpectedly-shaped payload."""
    resp = session.get(COLLINFO, timeout=getattr(session, "request_timeout", 30))
    resp.raise_for_status()
    info = resp.json()
    if not (isinstance(info, list) and info and isinstance(info[0], dict)):
        raise RuntimeError("collinfo.json returned an unexpected shape")
    url = info[0].get("cdx-api")
    if not url:
        raise RuntimeError("collinfo.json first crawl has no cdx-api endpoint")
    return url


def discover_ats_boards(session, limit: int = 500, index_url: str | None = None) -> list[dict]:
    """Query the Common Crawl CDX index for each ATS domain and return deduped
    ``[{ats, token}]``. Best-effort throughout: a CDX bootstrap failure (total
    outage) yields no boards rather than crashing, and a failed domain query is
    skipped so a partial index outage still yields the domains that answered."""
    if index_url is None:
        try:
            index_url = _latest_index_url(session)
        except Exception as exc:  # noqa: BLE001 - a CDX outage yields no boards, not a crash
            print(f"Common Crawl index unavailable ({exc}) — no boards discovered.",
                  file=sys.stderr)
            return []
    seen: set[tuple[str, str]] = set()
    boards: list[dict] = []
    for domain in ATS_DOMAINS:
        try:
            resp = session.get(
                index_url,
                params={"url": f"{domain}/*", "output": "json",
                        "filter": "status:200", "fl": "url", "limit": limit},
                timeout=getattr(session, "request_timeout", 30))
            resp.raise_for_status()
            lines = resp.text.splitlines()
        except Exception:  # noqa: BLE001 - a dead domain query must not sink the sweep
            continue
        for entry in extract_ats_tokens(lines):
            key = (entry["ats"], entry["token"].lower())
            if key not in seen:
                seen.add(key)
                boards.append(entry)
    return boards


def load_discovered_boards(path: Path) -> list[dict]:
    """Read a previously-written discovered-boards file (``{ats_boards: [...]}``).
    Missing/malformed → empty (best-effort, never raises)."""
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(raw, dict):   # a hand-edited list/scalar is not a board file
        return []
    boards = raw.get("ats_boards") or []
    if not isinstance(boards, list):
        return []
    return [b for b in boards if isinstance(b, dict) and b.get("ats") and b.get("token")]


def write_discovered_boards(path: Path, boards: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"ats_boards": boards}, sort_keys=False))


DISCOVERED_FILE = "data/ats_boards.discovered.yaml"


def discover_ats_boards_command(root: Path, limit: int = 500) -> int:
    """CLI entry: crawl Common Crawl for ATS board tokens and write them to
    data/ats_boards.discovered.yaml, which discovery merges into the ats_boards
    seed on the next run."""
    from ..config import load_settings
    from ..http import make_session

    settings = load_settings(root / "config" / "settings.yaml")
    timeout = settings.get("fetch", {}).get("timeout_seconds", 30)
    session = make_session(timeout)
    boards = discover_ats_boards(session, limit=limit)
    out = root / DISCOVERED_FILE
    # Don't clobber a prior good file with an empty result (total CDX outage) —
    # keep what we had, mirroring the run-time discovery degradation guard.
    if not boards and out.exists():
        print(f"No boards discovered (Common Crawl unavailable?) — kept {out}.")
        return 0
    write_discovered_boards(out, boards)
    print(f"Discovered {len(boards)} ATS boards → {out}")
    return 0
