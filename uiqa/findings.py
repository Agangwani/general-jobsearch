"""The shared vocabulary between the three stages.

A *Finding* is a candidate problem an explorer saw (Stage 1). A *Verdict* is the
validator's ruling on it (Stage 2). Both are plain dicts on disk (findings.jsonl
and validation.json) so sub-agents — which only share the filesystem, not memory
— can hand work to each other, exactly like the existing validate-jobs loop
hands verdicts to the next pipeline run.

Findings dedup by a stable signature (area + kind + route + normalized message)
so the deterministic crawler and several explorer agents reporting the same
broken thing collapse into one item with one id.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

VALID_KINDS = {
    "page_error", "console_error", "console_warning", "http_error_4xx",
    "http_error_5xx", "request_failed", "server_error", "broken_ui", "ux",
}
VALID_SEVERITIES = {"high", "medium", "low"}
VALID_VERDICTS = {"confirmed", "works_as_intended", "flaky", "needs_info"}

# Strip volatile bits (ids, timestamps, ports, hex) so two reports of the same
# bug on different rows/runs share a signature. `kind` (e.g. http_error_4xx vs
# _5xx) still separates status classes even when their messages normalize alike.
_VOLATILE = re.compile(r"\b(\d{2,}|[0-9a-f]{8,}|\d{4}-\d{2}-\d{2}[t0-9:+.]*)\b", re.I)


def normalize(text: str) -> str:
    text = _VOLATILE.sub("#", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()[:200]


def signature(finding: dict[str, Any]) -> str:
    base = "|".join((finding.get("area", ""), finding.get("kind", ""),
                     route_template(finding.get("route", "")),
                     normalize(finding.get("detail", "") or finding.get("title", ""))))
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def route_template(route: str) -> str:
    """Collapse concrete ids to a template so /jobs/12 and /jobs/34 match."""
    route = (route or "").split("?")[0]
    return re.sub(r"/\d+", "/{id}", route)


def make_finding(*, area: str, route: str, kind: str, severity: str, title: str,
                 detail: str = "", repro: dict[str, Any] | None = None,
                 evidence: Iterable[str] = (), discovered_by: str = "crawler",
                 ) -> dict[str, Any]:
    f = {
        "area": area, "route": route, "kind": kind, "severity": severity,
        "title": title.strip()[:140], "detail": (detail or "")[:1500],
        "repro": repro or {}, "evidence": list(evidence),
        "discovered_by": discovered_by, "status": "candidate",
    }
    f["id"] = signature(f)
    return f


def merge(findings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup by signature, keeping the highest severity and unioning evidence /
    discoverers. Returns a stable, id-sorted list."""
    by_id: dict[str, dict[str, Any]] = {}
    order = {"high": 3, "medium": 2, "low": 1}
    for f in findings:
        f = dict(f)
        f.setdefault("id", signature(f))
        cur = by_id.get(f["id"])
        if cur is None:
            by_id[f["id"]] = f
            continue
        if order.get(f.get("severity", "low"), 0) > order.get(cur.get("severity", "low"), 0):
            cur["severity"] = f["severity"]
        cur["evidence"] = sorted(set(cur.get("evidence", [])) | set(f.get("evidence", [])))
        seen_by = {cur.get("discovered_by", ""), f.get("discovered_by", "")}
        cur["discovered_by"] = ", ".join(sorted(x for x in seen_by if x))
        if not cur.get("repro") and f.get("repro"):
            cur["repro"] = f["repro"]
    return sorted(by_id.values(), key=lambda x: (x["area"], x["id"]))


# ------------------------------------------------------------------- disk I/O
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # tolerate a half-written line from a crashed agent
    return out


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def write_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))
