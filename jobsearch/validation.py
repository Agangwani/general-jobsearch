"""Claude-assisted validation loop (no API cost — see docs/design-validation-loop.md).

Every run writes `reports/validation-request.md`: the top jobs plus top
near-misses with the claims a web-searching reviewer should verify. Once a
day, the user runs the `/validate-jobs` command in Claude Code (or pastes the
file into claude.ai); Claude verifies each posting via web search and writes
`data/validation.json`. The next run merges those verdicts into the report as
a confidence marker, and archives them to `data/validation-history/` so
labeled precision becomes a tracked time series.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .models import JobPosting

# How long a verdict stays applicable. Postings change fast; stale verdicts
# are dropped rather than shown with false confidence.
MAX_VERDICT_AGE_DAYS = 3

VERIFIED = "verified"   # ✓ live + senior + NYC all confirmed
MISMATCH = "mismatch"   # ⚠ live, but some claim didn't hold (see note)
STALE = "stale"         # ✗ posting closed/404
MARKS = {VERIFIED: "✓", MISMATCH: "⚠", STALE: "✗"}


def write_validation_request(
    jobs: list[JobPosting],
    near_miss: list[JobPosting],
    path: Path,
    top_jobs: int = 15,
    top_near_miss: int = 5,
) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        f"# Validation request — {today}",
        "",
        "For each posting below, verify via web search: (1) the posting is still",
        "open, (2) the role is genuinely senior-level, (3) it is NYC-based or",
        "NYC-hybrid, (4) the posted date is plausible. Then write verdicts to",
        "`data/validation.json` in the schema described at the bottom.",
        "",
        "## Top-ranked jobs",
        "",
    ]
    for idx, job in enumerate(jobs[:top_jobs], 1):
        lines += [
            f"### {idx}. {job.company} — {job.title}",
            f"- key: `{job.key}`",
            f"- url: {job.url}",
            f"- claims: still-open | senior-level | NYC ({job.location}) | "
            f"posted {job.posted_at.date().isoformat() if job.posted_at else 'unknown'}",
            "",
        ]
    if near_miss:
        lines += [
            "## Near-misses (also verify the filter reason)",
            "",
        ]
        for idx, job in enumerate(near_miss[:top_near_miss], 1):
            lines += [
                f"### N{idx}. {job.company} — {job.title}",
                f"- key: `{job.key}`",
                f"- url: {job.url}",
                f"- filtered because: `{job.filter_reason}` — is that accurate? "
                "(e.g. for UNLEVELED_TITLE: does the page show a level or years requirement?)",
                "",
            ]
    lines += [
        "## Response schema (`data/validation.json`)",
        "",
        "```json",
        json.dumps({
            "checked_at": f"{today}T00:00:00Z",
            "verdicts": [{
                "key": "<key from above>",
                "live": True,
                "senior_confirmed": True,
                "nyc_confirmed": True,
                "fit_assessment": "<one line: why this does/doesn't match the resume>",
                "flags": ["<anything off — e.g. multi-state remote pool, reposted listing>"],
                "confidence": 0.9,
            }],
        }, indent=2),
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def _verdict_status(verdict: dict) -> str:
    if not verdict.get("live", True):
        return STALE
    if (verdict.get("senior_confirmed") is False
            or verdict.get("nyc_confirmed") is False
            or verdict.get("flags")):
        return MISMATCH
    return VERIFIED


def load_verdicts(path: Path, now: datetime | None = None) -> dict[str, dict]:
    """Return {job_key: verdict} from data/validation.json, dropping expired files."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        checked_at = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return {}
    now = now or datetime.now(timezone.utc)
    if (now - checked_at).days > MAX_VERDICT_AGE_DAYS:
        return {}
    return {v["key"]: v for v in data.get("verdicts", []) if v.get("key")}


def apply_verdicts(jobs: list[JobPosting], verdicts: dict[str, dict]) -> dict[str, int]:
    """Annotate jobs in place; returns {status: count} for the precision line."""
    tally = {VERIFIED: 0, MISMATCH: 0, STALE: 0}
    for job in jobs:
        verdict = verdicts.get(job.key)
        if not verdict:
            continue
        status = _verdict_status(verdict)
        job.validation = status
        flags = verdict.get("flags") or []
        job.validation_note = "; ".join(flags) if flags else verdict.get("fit_assessment", "")
        tally[status] += 1
    return tally


def archive_validation(path: Path, history_dir: Path) -> None:
    """Keep every day's verdicts so labeled precision is a time series."""
    if not path.exists():
        return
    try:
        checked = json.loads(path.read_text()).get("checked_at", "")[:10]
    except (json.JSONDecodeError, OSError):
        return
    if not checked:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    target = history_dir / f"{checked}.json"
    if not target.exists():
        shutil.copy(path, target)
