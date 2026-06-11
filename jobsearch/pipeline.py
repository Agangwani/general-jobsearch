from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .browser import BrowserRuntime, BrowserUnavailable
from .config import load_companies, load_settings
from .fetchers import BROWSER_FETCHERS, FETCHERS
from .filters import JobFilter
from .http import make_session
from .models import Company, FetchError, JobPosting
from .report import render_markdown, write_reports
from .scoring import apply_recency, rank_companies, score_jobs
from .state import load_seen, mark_new, update_seen


def fetch_all(
    companies: list[Company], settings: dict
) -> tuple[list[JobPosting], list[FetchError]]:
    timeout = settings.get("fetch", {}).get("timeout_seconds", 30)
    max_workers = settings.get("fetch", {}).get("max_workers", 8)
    jobs: list[JobPosting] = []
    errors: list[FetchError] = []

    enabled = [c for c in companies if c.enabled]
    api_companies = [c for c in enabled if c.ats in FETCHERS]
    browser_jobs: list[tuple[Company, str, str]] = [  # (company, browser ats, primary error)
        (c, c.ats, "") for c in enabled if c.ats in BROWSER_FETCHERS
    ]
    for company in enabled:
        if company.ats not in FETCHERS and company.ats not in BROWSER_FETCHERS:
            errors.append(FetchError(company.name, f"unknown ats type: {company.ats}"))

    def fetch_one(company: Company) -> list[JobPosting]:
        session = make_session(timeout)
        try:
            return FETCHERS[company.ats](company, session, settings)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, c): c for c in api_companies}
        for future in as_completed(futures):
            company = futures[future]
            try:
                fetched = future.result()
                jobs.extend(fetched)
                print(f"  {company.name}: {len(fetched)} postings", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 — one bad board must not sink the run
                error = f"{type(exc).__name__}: {exc}"
                fallback = company.params.get("fallback")
                if fallback in BROWSER_FETCHERS:
                    print(f"  {company.name}: API failed ({exc}); queueing browser fallback", file=sys.stderr)
                    browser_jobs.append((company, fallback, error))
                else:
                    errors.append(FetchError(company.name, error))
                    print(f"  {company.name}: ERROR {exc}", file=sys.stderr)

    if browser_jobs:
        browser_timeout = settings.get("fetch", {}).get("browser_timeout_seconds", 45)
        try:
            with BrowserRuntime(browser_timeout) as runtime:
                for company, ats, primary_error in browser_jobs:
                    try:
                        fetched = BROWSER_FETCHERS[ats](company, runtime, settings)
                        jobs.extend(fetched)
                        print(f"  {company.name}: {len(fetched)} postings (browser)", file=sys.stderr)
                    except Exception as exc:  # noqa: BLE001
                        error = f"{type(exc).__name__}: {exc}"
                        if primary_error:
                            error = f"API: {primary_error}; browser fallback: {error}"
                        errors.append(FetchError(company.name, error))
                        print(f"  {company.name}: ERROR {exc}", file=sys.stderr)
        except BrowserUnavailable as exc:
            for company, _, primary_error in browser_jobs:
                error = f"{exc}" if not primary_error else f"API: {primary_error}; {exc}"
                errors.append(FetchError(company.name, error))
            print(f"  Browser pass skipped: {exc}", file=sys.stderr)

    return jobs, errors


def dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    seen: set[str] = set()
    unique = []
    for job in jobs:
        if job.key in seen:
            continue
        seen.add(job.key)
        unique.append(job)
    return unique


def run(root: Path) -> int:
    settings = load_settings(root / "config" / "settings.yaml")
    companies, manual_check = load_companies(root / "config" / "companies.yaml")
    resume_text = (root / settings["resume"]).read_text()

    print(f"Fetching boards for {sum(c.enabled for c in companies)} companies...", file=sys.stderr)
    jobs, errors = fetch_all(companies, settings)
    jobs = dedupe(jobs)
    print(f"Fetched {len(jobs)} postings; filtering...", file=sys.stderr)

    job_filter = JobFilter(settings["search"])
    jobs = job_filter.apply(jobs)

    ranking = settings["ranking"]
    max_age = ranking.get("max_age_days", 45)
    if max_age:
        jobs = [j for j in jobs if (j.age_days() or 0) <= max_age]
    print(f"{len(jobs)} NYC senior-SWE postings after filters; scoring...", file=sys.stderr)

    score_jobs(resume_text, jobs, clusters=ranking.get("clusters", "auto"))
    apply_recency(
        jobs,
        half_life_days=ranking.get("half_life_days", 7),
        unknown_age_days=ranking.get("unknown_age_days", 14),
    )
    company_fit = rank_companies(jobs, top_n=ranking.get("company_top_n", 3))

    state_path = root / settings["output"].get("state_file", "data/seen_jobs.json")
    seen = load_seen(state_path)
    mark_new(jobs, seen)
    update_seen(jobs, seen, state_path)

    markdown = render_markdown(
        jobs, company_fit, companies, manual_check, errors,
        top_jobs=ranking.get("top_jobs", 100),
    )
    out_dir = root / settings["output"].get("reports_dir", "reports")
    written = write_reports(out_dir, markdown, jobs, company_fit)

    print(f"Wrote {', '.join(str(p) for p in written)}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} boards failed: {', '.join(e.company for e in errors)}", file=sys.stderr)
    return 0


def verify(root: Path) -> int:
    """Hit every enabled board once and report reachability — run this after
    editing companies.yaml to catch wrong board slugs."""
    settings = load_settings(root / "config" / "settings.yaml")
    companies, _ = load_companies(root / "config" / "companies.yaml")
    jobs, errors = fetch_all(companies, settings)
    ok = {c.name for c in companies if c.enabled} - {e.company for e in errors}
    print(f"\nOK ({len(ok)}): {', '.join(sorted(ok))}")
    if errors:
        print(f"\nFAILED ({len(errors)}):")
        for err in sorted(errors, key=lambda e: e.company):
            print(f"  {err.company}: {err.error[:160]}")
    print(f"\nTotal postings fetched: {len(jobs)}")
    return 1 if errors else 0
