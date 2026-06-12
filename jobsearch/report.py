from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Company, FetchError, JobPosting


def _fmt_date(job: JobPosting) -> str:
    return job.posted_at.date().isoformat() if job.posted_at else "unknown"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").strip()


def _skew_warning(jobs: list[JobPosting], top_k: int = 10, threshold: float = 0.4) -> str:
    """One company holding > threshold of the top rows is a scoring-skew smell
    (docs/analysis-scoring-skew.md)."""
    head = jobs[:top_k]
    if len(head) < top_k:
        return ""
    counts: dict[str, int] = {}
    for job in head:
        counts[job.company] = counts.get(job.company, 0) + 1
    company, n = max(counts.items(), key=lambda kv: kv[1])
    if n / len(head) > threshold:
        return (f"⚠️ **Skew check**: {company} holds {n} of the top {len(head)} rows "
                f"— treat its ranking with suspicion (see docs/analysis-scoring-skew.md).")
    return ""


def render_markdown(
    jobs: list[JobPosting],
    company_fit: dict[str, float],
    companies: list[Company],
    manual_check: list[dict],
    errors: list[FetchError],
    top_jobs: int,
    near_miss: list[JobPosting] = (),
    funnel: dict[str, dict] | None = None,
    cluster_names: dict[int, str] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        f"# NYC Senior Software Engineer Job Report — {now.date().isoformat()}",
        "",
        f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')}. "
        f"{len(jobs)} matching postings across {len(company_fit)} companies. "
        "Fit scores are relative (best match of the day = 100); job order is "
        "fit weighted by recency, so newly posted roles rise to the top.",
        "",
        "## Companies ranked by resume fit",
        "",
        "| # | Company | Fit | Tags | Matching roles | Job board |",
        "|---|---------|-----|------|----------------|-----------|",
    ]

    by_name = {c.name: c for c in companies}
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.company] = counts.get(job.company, 0) + 1

    ranked = sorted(company_fit.items(), key=lambda kv: -kv[1])
    for idx, (name, fit) in enumerate(ranked, 1):
        company = by_name.get(name)
        tags = ", ".join(company.tags) if company else ""
        link = f"[board]({company.careers_url})" if company and company.careers_url else ""
        lines.append(f"| {idx} | {name} | {fit} | {tags} | {counts.get(name, 0)} | {link} |")

    no_match = sorted(c.name for c in companies if c.enabled and c.name not in company_fit)
    if no_match:
        lines += ["", "Companies with no matching NYC senior-SWE postings today: " + ", ".join(no_match) + "."]

    warning = _skew_warning(jobs)
    if warning:
        lines += ["", warning]

    checked = any(job.validation for job in jobs)
    conf_header = "| # | Posted | New | Conf | Fit | Company | Title | Location |" if checked else \
                  "| # | Posted | New | Fit | Company | Title | Location |"
    conf_rule = "|---|--------|-----|------|-----|---------|-------|----------|" if checked else \
                "|---|--------|-----|-----|---------|-------|----------|"
    lines += ["", f"## Top {min(top_jobs, len(jobs))} jobs (recency-weighted fit)", ""]
    if checked:
        lines.append("Conf: ✓ Claude-verified live/senior/NYC · ⚠ mismatch found · "
                     "✗ posting closed · blank = unchecked (see reports/validation-request.md).")
        lines.append("")
    lines += [conf_header, conf_rule]
    from .validation import MARKS  # local import to avoid a cycle at module load
    for idx, job in enumerate(jobs[:top_jobs], 1):
        new = "🆕" if job.is_new else ""
        title = f"[{_md_escape(job.title)}]({job.url})" if job.url else _md_escape(job.title)
        conf = f" {MARKS.get(job.validation, '')} |" if checked else ""
        lines.append(
            f"| {idx} | {_fmt_date(job)} | {new} |{conf} {job.fit_score} | {job.company} "
            f"| {title} | {_md_escape(job.location)[:60]} |"
        )

    if near_miss:
        lines += [
            "",
            f"## Near-miss roles ({len(near_miss)}) — broadened search",
            "",
            "Engineering roles that failed exactly one filter gate, scored with the "
            "same model. If these consistently outscore the main table, the filter "
            "is too tight in that direction (docs/analysis-zero-match-companies.md).",
            "",
            "| # | Posted | Fit | Company | Title | Location | Why filtered |",
            "|---|--------|-----|---------|-------|----------|--------------|",
        ]
        for idx, job in enumerate(near_miss, 1):
            title = f"[{_md_escape(job.title)}]({job.url})" if job.url else _md_escape(job.title)
            lines.append(
                f"| {idx} | {_fmt_date(job)} | {job.fit_score} | {job.company} "
                f"| {title} | {_md_escape(job.location)[:45]} | `{job.filter_reason}` |"
            )

    if funnel:
        lines += [
            "",
            "## Fetch & filter funnel",
            "",
            "Why companies show zero matches: no fetch (see errors below), or "
            "fetched-but-filtered (this table).",
            "",
            "| Company | Fetched | Title ✓ | Location ✓ | Matched | Near-miss | Aged out |",
            "|---------|---------|---------|------------|---------|-----------|----------|",
        ]
        for name, row in sorted(funnel.items(), key=lambda kv: -kv[1]["fetched"]):
            lines.append(
                f"| {name} | {row['fetched']} | {row['title_pass']} | {row['loc_pass']} "
                f"| {row['matched']} | {row['near_miss']} | {row.get('aged_out', 0)} |"
            )

    if cluster_names:
        used = {job.cluster for job in jobs} | {job.cluster for job in near_miss}
        relevant = {c: t for c, t in cluster_names.items() if c in used}
        if relevant:
            lines += ["", "## Cluster topics", ""]
            lines += [f"- cluster {c}: {t}" for c, t in sorted(relevant.items())]

    new_jobs = [job for job in jobs if job.is_new]
    lines += ["", f"## New since last run ({len(new_jobs)})", ""]
    if new_jobs:
        for job in new_jobs[:50]:
            lines.append(f"- **{job.company}** — [{_md_escape(job.title)}]({job.url}) ({_fmt_date(job)}, fit {job.fit_score})")
    else:
        lines.append("Nothing new since the last run.")

    if errors:
        lines += ["", "## Boards that need attention", ""]
        lines += [f"- **{err.company}**: `{err.error[:200]}`" for err in errors]

    if manual_check:
        lines += [
            "",
            "## Check manually (no scrapable board)",
            "",
        ]
        lines += [f"- [{entry['name']}]({entry.get('careers_url', '')})" for entry in manual_check]

    lines.append("")
    return "\n".join(lines)


def _job_json(job: JobPosting) -> dict:
    return {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "url": job.url,
        "posted": _fmt_date(job),
        "fit": job.fit_score,
        "rank_score": job.rank_score,
        "new": job.is_new,
        "cluster": job.cluster,
        "key": job.key,
        "filter_reason": job.filter_reason,
        "validation": job.validation,
        "validation_note": job.validation_note,
    }


def write_reports(
    out_dir: Path,
    markdown: str,
    jobs: list[JobPosting],
    company_fit: dict[str, float],
    near_miss: list[JobPosting] = (),
    funnel: dict[str, dict] | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    written = []

    for name in (f"{today}.md", "latest.md"):
        path = out_dir / name
        path.write_text(markdown)
        written.append(path)

    csv_path = out_dir / "latest.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["rank", "posted", "new", "fit", "rank_score", "company", "title", "location", "url"])
        for idx, job in enumerate(jobs, 1):
            writer.writerow([
                idx, _fmt_date(job), job.is_new, job.fit_score, job.rank_score,
                job.company, job.title, job.location, job.url,
            ])
    written.append(csv_path)

    json_path = out_dir / "latest.json"
    json_path.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "company_fit": company_fit,
        "jobs": [_job_json(job) for job in jobs],
        "near_miss": [_job_json(job) for job in near_miss],
        "funnel": funnel or {},
    }, indent=2) + "\n")
    written.append(json_path)
    return written
