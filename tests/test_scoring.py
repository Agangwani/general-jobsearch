from datetime import datetime, timedelta, timezone

from jobsearch.models import JobPosting
from jobsearch.scoring import apply_recency, rank_companies, score_jobs

RESUME = """Senior software engineer with AWS Lambda, Step Functions, DynamoDB,
Python microservices, Kafka, distributed systems, fraud detection, observability,
OpenTelemetry, serverless backend architecture, fintech payments."""

BACKEND_DESC = """Build backend microservices in Python on AWS Lambda and DynamoDB.
Event-driven distributed systems with Kafka and SQS. Observability, serverless,
fraud and payments platform experience preferred."""

FRONTEND_DESC = """Craft delightful user interfaces in React and TypeScript.
CSS animation, design systems, accessibility, Figma collaboration, pixel-perfect
web experiences, component libraries, storybook."""


def make_jobs():
    jobs = []
    for i in range(6):
        jobs.append(JobPosting(company=f"Backend{i % 2}", title="Senior Software Engineer, Platform",
                               location="New York", url="", job_id=f"b{i}", description=BACKEND_DESC + f" variant {i}"))
    for i in range(6):
        jobs.append(JobPosting(company=f"Frontend{i % 2}", title="Senior Software Engineer, Web UI",
                               location="New York", url="", job_id=f"f{i}", description=FRONTEND_DESC + f" variant {i}"))
    return jobs


def test_backend_jobs_score_higher():
    jobs = score_jobs(RESUME, make_jobs(), clusters=2)
    backend = [j.fit_score for j in jobs if j.company.startswith("Backend")]
    frontend = [j.fit_score for j in jobs if j.company.startswith("Frontend")]
    assert min(backend) > max(frontend)
    assert all(0 <= j.fit_score <= 100 for j in jobs)
    assert max(j.fit_score for j in jobs) == 100.0


def test_recency_outranks_stale_fit():
    now = datetime.now(timezone.utc)
    fresh = JobPosting(company="A", title="t", location="NY", url="", job_id="1",
                       posted_at=now - timedelta(days=1))
    fresh.fit_score = 70.0
    stale = JobPosting(company="B", title="t", location="NY", url="", job_id="2",
                       posted_at=now - timedelta(days=30))
    stale.fit_score = 95.0
    ordered = apply_recency([stale, fresh], half_life_days=7, unknown_age_days=14)
    assert ordered[0].company == "A"  # fresher posting wins despite lower fit
    assert ordered[0].rank_score > ordered[1].rank_score


def test_rank_companies_uses_top_n():
    jobs = []
    for score in (90, 80, 10, 10):
        job = JobPosting(company="Acme", title="t", location="NY", url="", job_id=str(score))
        job.fit_score = score
        jobs.append(job)
    fit = rank_companies(jobs, top_n=2)
    assert fit["Acme"] == 85.0
