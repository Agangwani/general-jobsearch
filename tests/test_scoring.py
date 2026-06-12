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


def test_full_corpus_scoring():
    """Scored jobs can be a subset of a larger corpus that defines the space."""
    corpus = make_jobs()
    subset = corpus[:3] + corpus[6:9]  # 3 backend + 3 frontend
    subset, topics = score_jobs(RESUME, subset, clusters=2, corpus=corpus, return_topics=True)
    backend = [j.fit_score for j in subset if j.company.startswith("Backend")]
    frontend = [j.fit_score for j in subset if j.company.startswith("Frontend")]
    assert min(backend) > max(frontend)
    assert max(j.fit_score for j in subset) == 100.0
    assert all(j.cluster >= 0 for j in subset)
    assert set(topics) == {0, 1} and all(topics.values())


def test_boilerplate_stripped():
    from jobsearch.scoring import strip_company_boilerplate

    boiler = "Acme is the leading observability platform for cloud infrastructure monitoring."
    jobs = [
        JobPosting(company="Acme", title="SWE", location="NY", url="", job_id=str(i),
                   description=f"{boiler} Role {i}: build the {role} system.")
        for i, role in enumerate(["billing", "search", "ingest"])
    ]
    # A company with a single posting keeps its description untouched.
    solo = JobPosting(company="Solo", title="SWE", location="NY", url="", job_id="s",
                      description=f"{boiler} Unique role.")
    cleaned = strip_company_boilerplate(jobs + [solo])
    for job in jobs:
        assert boiler not in cleaned[job.key]
        assert "system" in cleaned[job.key]  # role-specific text survives
    assert boiler in cleaned[solo.key]


def test_boilerplate_changes_scores():
    """Shared marketing text matching the resume must not lift a whole company."""
    boiler = ("We build observability, distributed systems, Kafka, AWS Lambda, "
              "DynamoDB, serverless microservices at massive scale. " * 3)
    jobs = []
    for i in range(4):  # boilerplate-heavy company, role text unrelated to resume
        jobs.append(JobPosting(company="Hype", title="Senior Software Engineer",
                               location="New York", url="", job_id=f"h{i}",
                               description=boiler + f" Role: CSS design systems, marketing pages variant {i}."))
    for i in range(4):  # no boilerplate, genuinely relevant role text
        jobs.append(JobPosting(company="Real", title="Senior Software Engineer",
                               location="New York", url="", job_id=f"r{i}",
                               description=BACKEND_DESC + f" variant {i}"))
    score_jobs(RESUME, jobs, clusters=2)
    hype = max(j.fit_score for j in jobs if j.company == "Hype")
    real = max(j.fit_score for j in jobs if j.company == "Real")
    assert real > hype
