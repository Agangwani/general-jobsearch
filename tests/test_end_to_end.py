"""Offline end-to-end check: scoring + recency + state + report rendering."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobsearch.models import Company, FetchError, JobPosting
from jobsearch.report import render_markdown, write_reports
from jobsearch.scoring import apply_recency, rank_companies, score_jobs
from jobsearch.state import load_seen, mark_new, update_seen

RESUME = (Path(__file__).parent.parent / "data" / "sample_resume.txt").read_text()

DESCRIPTIONS = {
    "Datadog": "Backend distributed systems in Go and Python, observability pipelines, Kafka, high-scale metrics ingestion on AWS.",
    "Ramp": "Python backend microservices for fintech payments, AWS serverless, DynamoDB, fraud and risk decisioning systems.",
    "Figma": "Browser graphics engine in C++ and WebAssembly, rendering pipelines, UI performance.",
    "Amazon": "AWS Lambda and Step Functions services, DynamoDB, event-driven architecture, large scale distributed systems.",
}


def make_jobs():
    now = datetime.now(timezone.utc)
    ages = {"Datadog": 1, "Ramp": 0, "Figma": 2, "Amazon": 20}
    jobs = []
    for i, (company, desc) in enumerate(DESCRIPTIONS.items()):
        for variant in range(3):
            jobs.append(JobPosting(
                company=company,
                title="Senior Software Engineer",
                location="New York, NY",
                url=f"https://example.com/{company}/{variant}",
                job_id=f"{company}-{variant}",
                description=f"{desc} team {variant}",
                posted_at=now - timedelta(days=ages[company] + variant),
                source="test",
            ))
    return jobs


def test_pipeline_end_to_end(tmp_path):
    jobs = make_jobs()
    score_jobs(RESUME, jobs, clusters=2)
    apply_recency(jobs, half_life_days=7, unknown_age_days=14)
    company_fit = rank_companies(jobs, top_n=3)

    # Fintech/AWS-backend companies should fit this resume better than a
    # browser-graphics role.
    assert company_fit["Ramp"] > company_fit["Figma"]
    assert company_fit["Amazon"] > company_fit["Figma"]
    # Amazon has great fit but 20-day-old postings; fresh Ramp roles must
    # outrank it in the job ordering.
    assert jobs[0].company in {"Ramp", "Datadog"}

    state = tmp_path / "seen.json"
    seen = load_seen(state)
    mark_new(jobs, seen)
    assert all(job.is_new for job in jobs)
    update_seen(jobs, seen, state)
    seen2 = load_seen(state)
    mark_new(jobs, seen2)
    assert not any(job.is_new for job in jobs)

    near = JobPosting(
        company="Stripe", title="Backend Engineer, Payments", location="New York, NY",
        url="https://example.com/stripe/1", job_id="s1",
        description="6+ years building payment APIs.", source="test",
    )
    near.fit_score = 55.0
    near.filter_reason = "UNLEVELED_TITLE"
    funnel = {"Stripe": {"fetched": 498, "title_pass": 0, "loc_pass": 132, "matched": 0, "near_miss": 41}}

    companies = [Company(name=n, ats="test", tags=["top50"], careers_url="https://example.com") for n in DESCRIPTIONS]
    markdown = render_markdown(
        jobs, company_fit, companies,
        manual_check=[{"name": "Jane Street", "careers_url": "https://example.com"}],
        errors=[FetchError("BrokenCo", "HTTPError: 404")],
        top_jobs=50,
        near_miss=[near],
        funnel=funnel,
        cluster_names={0: "backend, aws", 1: "frontend, css"},
    )
    assert "Companies ranked by resume fit" in markdown
    assert "Jane Street" in markdown
    assert "BrokenCo" in markdown
    assert "Near-miss roles" in markdown and "UNLEVELED_TITLE" in markdown
    assert "Fetch & filter funnel" in markdown and "| Stripe | 498 |" in markdown
    assert "Cluster topics" in markdown

    written = write_reports(tmp_path / "reports", markdown, jobs, company_fit,
                            near_miss=[near], funnel=funnel)
    names = {p.name for p in written}
    assert "latest.md" in names and "latest.csv" in names and "latest.json" in names

    import json
    payload = json.loads((tmp_path / "reports" / "latest.json").read_text())
    assert payload["near_miss"][0]["filter_reason"] == "UNLEVELED_TITLE"
    assert payload["funnel"]["Stripe"]["fetched"] == 498
