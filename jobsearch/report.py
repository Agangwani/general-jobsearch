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


def render_markdown(
    jobs: list[JobPosting],
    company_fit: dict[str, float],
    companies: list[Company],
    manual_check: list[dict],
    errors: list[FetchError],
    top_jobs: int,
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

    lines += [
        "",
        f"## Top {min(top_jobs, len(jobs))} jobs (recency-weighted fit)",
        "",
        "| # | Posted | New | Fit | Company | Title | Location |",
        "|---|--------|-----|-----|---------|-------|----------|",
    ]
    for idx, job in enumerate(jobs[:top_jobs], 1):
        new = "🆕" if job.is_new else ""
        title = f"[{_md_escape(job.title)}]({job.url})" if job.url else _md_escape(job.title)
        lines.append(
            f"| {idx} | {_fmt_date(job)} | {new} | {job.fit_score} | {job.company} "
            f"| {title} | {_md_escape(job.location)[:60]} |"
        )

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


def write_reports(
    out_dir: Path,
    markdown: str,
    jobs: list[JobPosting],
    company_fit: dict[str, float],
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
        "jobs": [
            {
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "url": job.url,
                "posted": _fmt_date(job),
                "fit": job.fit_score,
                "rank_score": job.rank_score,
                "new": job.is_new,
                "cluster": job.cluster,
            }
            for job in jobs
        ],
    }, indent=2) + "\n")
    written.append(json_path)
    return written
