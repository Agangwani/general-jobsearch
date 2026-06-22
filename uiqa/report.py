"""Run directory + human/machine summaries.

Each run lives under reports/uiqa/<timestamp>/ (gitignored, like every other
report) with the artifacts the three stages exchange:

  action-index.json   every route → every actionable element (Stage 1 coverage)
  session-log.jsonl   every step the crawler/agents took, with captured errors
  findings.jsonl      candidate problems (appended by crawler + explorer agents)
  findings.json       deduped, merged view (the validator's input)
  validation.json     per-finding verdicts (Stage 2 output, fixer's input)
  scenarios/          reusable journey files (a finding's repro lives here)
  screenshots/        evidence
  summary.md          the human-readable digest
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import findings as F


class RunDir:
    def __init__(self, root: Path, run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.base = Path(root) / "reports" / "uiqa" / self.run_id
        for sub in ("", "scenarios", "screenshots", "incoming"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)
        self._update_latest(root)

    def _update_latest(self, root: Path) -> None:
        link = Path(root) / "reports" / "uiqa" / "latest"
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(self.base.name)
        except OSError:
            pass  # symlinks may be unavailable; the timestamped dir still works

    # --------------------------------------------------------------- artifacts
    @property
    def action_index(self) -> Path:
        return self.base / "action-index.json"

    @property
    def session_log(self) -> Path:
        return self.base / "session-log.jsonl"

    @property
    def findings_jsonl(self) -> Path:
        return self.base / "findings.jsonl"

    @property
    def findings_json(self) -> Path:
        return self.base / "findings.json"

    @property
    def validation_json(self) -> Path:
        return self.base / "validation.json"

    def log_step(self, record: dict[str, Any]) -> None:
        F.append_jsonl(self.session_log, record)

    def add_finding(self, finding: dict[str, Any]) -> None:
        F.append_jsonl(self.findings_jsonl, finding)

    def consolidate(self) -> list[dict[str, Any]]:
        """Merge every finding — those appended to findings.jsonl by the crawler
        and any dropped as incoming/*.json by explorer sub-agents — into one
        deduped findings.json. Sub-agents write a file rather than appending so
        there's no shared-file contention or shell-quoting to get wrong."""
        raw = F.load_jsonl(self.findings_jsonl)
        for jf in sorted((self.base / "incoming").glob("*.json")):
            try:
                obj = json.loads(jf.read_text())
            except ValueError:
                continue
            raw.extend(obj if isinstance(obj, list) else [obj])
        merged = F.merge(raw)
        F.write_json(self.findings_json, merged)
        return merged

    def write_action_index(self, index: dict[str, Any]) -> None:
        F.write_json(self.action_index, index)

    def save_scenario(self, scenario: dict[str, Any]) -> Path:
        name = F.signature({"title": scenario.get("name", "s"),
                             "detail": json.dumps(scenario.get("steps", []))})
        path = self.base / "scenarios" / f"{name}.json"
        path.write_text(json.dumps(scenario, indent=2))
        return path

    # ----------------------------------------------------------------- summary
    def write_summary(self, *, action_index: dict[str, Any],
                      findings: list[dict[str, Any]],
                      verdicts: list[dict[str, Any]] | None = None) -> Path:
        verdicts = verdicts or []
        v_by_id = {v["finding_id"]: v for v in verdicts}
        n_actions = sum(len(v) for v in action_index.values())
        sev = {s: sum(1 for f in findings if f["severity"] == s)
               for s in ("high", "medium", "low")}
        lines = [
            f"# UI-QA run {self.run_id}", "",
            f"- Routes explored: **{len(action_index)}**",
            f"- Actions indexed: **{n_actions}**",
            f"- Candidate findings: **{len(findings)}** "
            f"(high {sev['high']} · medium {sev['medium']} · low {sev['low']})",
        ]
        if verdicts:
            confirmed = sum(1 for v in verdicts if v["verdict"] == "confirmed")
            lines.append(f"- Validated: **{len(verdicts)}** "
                         f"(confirmed {confirmed})")
        lines += ["", "## Findings", ""]
        if not findings:
            lines.append("_No problems detected._")
        for f in sorted(findings, key=_sev_key):
            v = v_by_id.get(f["id"])
            verdict = f" — **{v['verdict']}**" if v else ""
            lines.append(f"### [{f['severity'].upper()}] {f['title']}{verdict}")
            lines.append(f"- id: `{f['id']}` · area: `{f['area']}` · "
                         f"route: `{f['route']}` · kind: `{f['kind']}`")
            if f.get("detail"):
                lines.append(f"- detail: {f['detail'][:300]}")
            if v and v.get("root_cause"):
                lines.append(f"- root cause: {v['root_cause']}")
            if v and v.get("suggested_fix"):
                lines.append(f"- suggested fix: {v['suggested_fix']}")
            lines.append("")
        path = self.base / "summary.md"
        path.write_text("\n".join(lines))
        return path


def _sev_key(f: dict[str, Any]) -> tuple:
    order = {"high": 0, "medium": 1, "low": 2}
    return (order.get(f["severity"], 3), f["area"], f["id"])
