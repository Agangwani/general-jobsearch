from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .browser import BrowserRuntime, BrowserUnavailable
from .config import load_registry, load_settings
from .corpus import write_snapshot
from .fetchers import BROWSER_FETCHERS, FETCHERS
from .filters import MATCH, NEAR_LOCATION, NEAR_TITLE, JobFilter, build_funnel
from .http import make_session
from .models import Company, FetchError, JobPosting
from .report import render_markdown, write_clustering, write_reports, write_run_log
from .scoring import apply_recency, rank_companies, score_jobs
from .state import load_seen, mark_new, update_seen
from .validation import (
    apply_verdicts,
    archive_validation,
    load_verdicts,
    write_validation_request,
)


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


def _build_runlog(targeting, resume_text, is_sample, settings, companies,
                  all_jobs, jobs, near_miss, company_fit, errors) -> dict:
    """Assemble the structured run record written to reports/run-log.json."""
    from datetime import datetime, timezone

    enabled = [c for c in companies if c.enabled]
    fetched_by_company: dict[str, int] = {}
    for job in all_jobs:
        fetched_by_company[job.company] = fetched_by_company.get(job.company, 0) + 1
    errored = {e.company for e in errors}
    zero_fetch = sorted(c.name for c in enabled
                        if c.name not in fetched_by_company and c.name not in errored)
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "resume": {
            "source": "sample" if is_sample else settings.get("resume", "data/resume.txt"),
            "chars": len(resume_text),
        },
        "targeting": targeting,
        "search": {
            "query": settings["search"].get("query", ""),
            "locations": settings["search"].get("locations", []),
        },
        "companies": {
            "enabled": len(enabled),
            "with_postings": sorted(fetched_by_company),
            "fetched_by_company": dict(sorted(
                fetched_by_company.items(), key=lambda kv: -kv[1])),
            "zero_fetch": zero_fetch,
            "errored": [{"company": e.company, "error": e.error[:300]} for e in errors],
        },
        "totals": {
            "fetched": len(all_jobs),
            "matched": len(jobs),
            "near_miss": len(near_miss),
        },
        "company_fit": dict(sorted(company_fit.items(), key=lambda kv: -kv[1])),
        "top_jobs": [
            {"company": j.company, "title": j.title, "location": j.location,
             "fit": j.fit_score, "rank_score": j.rank_score}
            for j in jobs[:30]
        ],
    }


def _write_role_profile(root: Path, settings: dict, profile) -> None:
    """Persist the derived profile so the UI / report can show what the run
    targeted (data/role_profile.json, gitignored)."""
    import json

    path = root / settings.get("output", {}).get("role_profile_file", "data/role_profile.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), indent=2))


def apply_startup_search_knobs(settings: dict, cfg: dict) -> None:
    """Apply the startup track's relaxed search/ranking knobs onto `settings`
    in place, only for keys the startups: config actually sets. Safe to call
    before role targeting — none of these are overwritten by apply_profile."""
    search = settings.setdefault("search", {})
    ranking = settings.setdefault("ranking", {})
    if "include_remote" in cfg:
        search["include_remote"] = bool(cfg["include_remote"])
    if "remote_min_pay" in cfg:
        search["remote_min_pay"] = int(cfg["remote_min_pay"] or 0)
    for key in ("max_age_days", "near_miss_count"):
        if key in cfg:
            ranking[key] = cfg[key]


_ENGINEERING_HINTS = (
    "engineer", "developer", "software", "data", "machine learning",
    "ml", "devops", "sre", "programmer", "technical",
)


def _profile_is_engineering(profile) -> bool:
    """Whether the resume-matched role is engineering-ish, so the SWE-flavored
    extra_title_include patterns are appropriate. A None profile means manual /
    low-confidence targeting, which falls back to the SWE-default settings, so
    appending is consistent there too."""
    if profile is None:
        return True
    hay = " ".join(getattr(profile, "occupations", []) or []).lower()
    return any(hint in hay for hint in _ENGINEERING_HINTS)


def append_startup_titles(settings: dict, cfg: dict) -> int:
    """Append cfg['extra_title_include'] onto the (already role-targeted)
    title_include in place. Returns how many patterns were added. Must run
    AFTER apply_profile so the patterns survive its overwrite."""
    extra = cfg.get("extra_title_include") or []
    if not extra:
        return 0
    search = settings.setdefault("search", {})
    search["title_include"] = list(search.get("title_include") or []) + list(extra)
    return len(extra)


def run(root: Path, track_name: str = "main", user_id: str = "local") -> int:
    from .tracks import build_track

    settings = load_settings(root / "config" / "settings.yaml")
    track = build_track(root, settings, track_name, user_id)
    # The startups track chases its own city and can loosen the role/location
    # gate independently of the strict main search — startups are remote-heavy,
    # post flatter/unleveled titles, and post less frequently. These overrides
    # read from the startups: config block and touch only this run's in-memory
    # settings, so the two pipelines stay isolated (separate reports/seen/corpus).
    if track.is_startup:
        if track.locations:
            settings["search"]["locations"] = track.locations
        apply_startup_search_knobs(settings, track.discovery)
    # Fresh companies every run: refresh the discovered registry before loading
    # it (gated by <track>.on_run + throttled by min_interval_minutes; best-
    # effort, so a discovery failure leaves the existing registry in place).
    from .company_discovery import maybe_run_discovery
    maybe_run_discovery(root, settings, track)
    # main: curated companies.yaml + the resume-tailored generated registry.
    # startups: the startup registry built by `discover-startups`.
    companies, manual_check = load_registry(root, settings, track)
    if track.is_startup:
        print(f"Startup track: {sum(c.enabled for c in companies)} startup "
              f"companies in scope (from {track.registry_file.name}).", file=sys.stderr)
    from .resume import load_resume_text
    resume_text, is_sample = load_resume_text(root, settings, user_id)
    if is_sample:
        print("NOTE: no resume found at data/resume.txt — scoring against the "
              "bundled sample resume. Upload yours on the /resume page of the "
              "UI (python -m jobsearch ui) for personalized results.", file=sys.stderr)

    # Re-target the search to the roles THIS resume is for: the matched
    # occupation's query and title filters replace the hand-tuned (SWE-by-
    # default) ones in settings.yaml. role_targeting: manual keeps settings.
    from .role_profile import apply_profile, resolve_profile
    profile = resolve_profile(root, settings, resume_text)
    if profile:
        settings["search"] = apply_profile(settings["search"], profile)
        _write_role_profile(root, settings, profile)
        targeting = {
            "occupations": profile.occupations,
            "query": profile.query,
            "seniority": profile.seniority,
            "matched_via": profile.matched_via,
            "skills": profile.skills,
            "title_include": len(profile.title_include),
            "title_exclude": len(profile.title_exclude),
            "scores": profile.scores,
        }
        print(f"Role profile [{profile.matched_via}]: {', '.join(profile.occupations)} "
              f"({profile.seniority}) — query '{profile.query}', "
              f"{len(profile.title_include)} title patterns. "
              f"Relevant skills: {', '.join(profile.skills[:10])}", file=sys.stderr)
    else:
        targeting = {"mode": "manual/low-confidence",
                     "query": settings["search"].get("query", "")}
        print("Role targeting off (manual or low-confidence match) — using the "
              "title filters in config/settings.yaml.", file=sys.stderr)

    # Startup-only extra title patterns (Founding / Forward-Deployed / Member of
    # Technical Staff / de-leveled SWE). Appended AFTER apply_profile, which
    # overwrites title_include with the occupation's senior-biased patterns, so
    # these survive and admit the flatter titles startups actually post. Gated on
    # an engineering-ish resume so a non-engineering profile (e.g. Customer
    # Success) doesn't get software-engineer titles grafted into its startup search.
    if track.is_startup and _profile_is_engineering(profile):
        added = append_startup_titles(settings, track.discovery)
        if added:
            print(f"Startup track: +{added} extra title patterns "
                  "(founding/forward-deployed/de-leveled).", file=sys.stderr)

    print(f"Fetching boards for {sum(c.enabled for c in companies)} companies...", file=sys.stderr)
    all_jobs, errors = fetch_all(companies, settings)
    all_jobs = dedupe(all_jobs)
    print(f"Fetched {len(all_jobs)} postings; filtering...", file=sys.stderr)

    output = settings.get("output", {})
    snapshot = write_snapshot(all_jobs, track.corpus_dir, output.get("corpus_retention_days", 14))
    print(f"Corpus snapshot: {snapshot}", file=sys.stderr)

    job_filter = JobFilter(settings["search"])
    ranking = settings["ranking"]
    max_age = ranking.get("max_age_days", 45)
    funnel = build_funnel(all_jobs, job_filter, max_age_days=max_age)
    jobs: list[JobPosting] = []
    near_miss: list[JobPosting] = []
    for job in all_jobs:
        status, reason = job_filter.classify(job)
        if status == MATCH:
            jobs.append(job)
        elif status in (NEAR_TITLE, NEAR_LOCATION):
            job.filter_reason = reason
            near_miss.append(job)

    if max_age:
        jobs = [j for j in jobs if (j.age_days() or 0) <= max_age]
        near_miss = [j for j in near_miss if (j.age_days() or 0) <= max_age]
    print(f"{len(jobs)} matching postings after filters "
          f"(+{len(near_miss)} near-miss); scoring...", file=sys.stderr)

    # Vectorizer + K-means are fit on the full fetched corpus; matched and
    # near-miss jobs are scored inside that space (docs/analysis-scoring-skew.md).
    # The explanation captures the same vectors for the /clusters visualization.
    _, cluster_names, clustering = score_jobs(
        resume_text,
        jobs + near_miss,
        clusters=ranking.get("clusters", "auto"),
        corpus=all_jobs,
        cluster_weight=ranking.get("cluster_weight", 0.05),
        decluster_company_signatures=ranking.get("decluster_company_signatures", True),
        match_backend=ranking.get("match_backend", "tfidf"),
        embedding_model=ranking.get("embedding_model"),
        return_topics=True,
        return_explanation=True,
    )
    apply_recency(
        jobs,
        half_life_days=ranking.get("half_life_days", 7),
        unknown_age_days=ranking.get("unknown_age_days", 14),
    )
    near_miss.sort(key=lambda j: -j.fit_score)
    near_miss = near_miss[: ranking.get("near_miss_count", 20)]
    company_fit = rank_companies(jobs, top_n=ranking.get("company_top_n", 3))

    state_path = track.state_file
    seen = load_seen(state_path)
    mark_new(jobs, seen)
    update_seen(jobs, seen, state_path)

    # Merge any fresh Claude verdicts (data/validation.json, written by the
    # /validate-jobs command) and archive them for the precision time series.
    # The startups track keeps its own verdict file so the two never collide.
    if track.is_startup:
        validation_path = root / "data" / "validation.startups.json"
        validation_history = root / "data" / "validation-history-startups"
    else:
        validation_path = root / output.get("validation_file", "data/validation.json")
        validation_history = root / output.get("validation_history_dir", "data/validation-history")
    verdicts = load_verdicts(validation_path)
    tally = apply_verdicts(jobs + near_miss, verdicts)
    archive_validation(validation_path, validation_history)
    if verdicts:
        print(f"Validation: {tally}", file=sys.stderr)

    markdown = render_markdown(
        jobs, company_fit, companies, manual_check, errors,
        top_jobs=ranking.get("top_jobs", 100),
        near_miss=near_miss,
        funnel=funnel,
        cluster_names=cluster_names,
        targeting=targeting,
    )
    out_dir = track.reports_dir
    written = write_reports(out_dir, markdown, jobs, company_fit, near_miss=near_miss, funnel=funnel)

    clustering_path = write_clustering(out_dir, clustering)
    if clustering_path:
        written.append(clustering_path)

    runlog = _build_runlog(
        targeting, resume_text, is_sample, settings, companies, all_jobs,
        jobs, near_miss, company_fit, errors)
    written.append(write_run_log(out_dir, runlog))

    request_path = write_validation_request(jobs, near_miss, out_dir / "validation-request.md")
    written.append(request_path)

    print(f"Wrote {', '.join(str(p) for p in written)}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} boards failed: {', '.join(e.company for e in errors)}", file=sys.stderr)
    return 0


def verify(root: Path, track_name: str = "main") -> int:
    """Hit every enabled board once and report reachability — run this after
    editing companies.yaml to catch wrong board slugs."""
    from .tracks import build_track

    settings = load_settings(root / "config" / "settings.yaml")
    track = build_track(root, settings, track_name)
    companies, _ = load_registry(root, settings, track)
    jobs, errors = fetch_all(companies, settings)
    ok = {c.name for c in companies if c.enabled} - {e.company for e in errors}
    print(f"\nOK ({len(ok)}): {', '.join(sorted(ok))}")
    if errors:
        print(f"\nFAILED ({len(errors)}):")
        for err in sorted(errors, key=lambda e: e.company):
            print(f"  {err.company}: {err.error[:160]}")
    print(f"\nTotal postings fetched: {len(jobs)}")
    return 1 if errors else 0
