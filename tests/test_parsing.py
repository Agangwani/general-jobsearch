from datetime import datetime, timedelta, timezone

from jobsearch.fetchers import ashby, greenhouse, lever, workday
from jobsearch.models import Company
from jobsearch.utils import parse_when, parse_workday_posted_on, strip_html


def test_strip_html():
    raw = "&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt;&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    assert strip_html(raw) == "Build APIs Python"


def test_parse_when_formats():
    assert parse_when("2026-06-10T12:00:00Z").year == 2026
    assert parse_when(1750000000000).year == 2025  # epoch ms
    assert parse_when("June 5, 2026").month == 6
    assert parse_when("not a date") is None
    assert parse_when(None) is None


def test_workday_posted_on():
    now = datetime(2026, 6, 11, tzinfo=timezone.utc)
    assert parse_workday_posted_on("Posted Today", now) == now
    assert parse_workday_posted_on("Posted Yesterday", now) == now - timedelta(days=1)
    assert parse_workday_posted_on("Posted 6 Days Ago", now) == now - timedelta(days=6)
    assert parse_workday_posted_on("Posted 30+ Days Ago", now) == now - timedelta(days=35)
    assert parse_workday_posted_on("") is None


def test_greenhouse_parse():
    raw = {
        "id": 123,
        "title": "Senior Software Engineer",
        "absolute_url": "https://boards.greenhouse.io/x/jobs/123",
        "location": {"name": "New York, NY"},
        "content": "&lt;p&gt;Backend role&lt;/p&gt;",
        "updated_at": "2026-06-01T00:00:00-04:00",
    }
    job = greenhouse.parse_job(raw, "Datadog")
    assert job.job_id == "123"
    assert job.location == "New York, NY"
    assert job.description == "Backend role"
    assert job.posted_at.year == 2026
    assert job.key == "greenhouse:Datadog:123"


def test_lever_parse():
    raw = {
        "id": "abc",
        "text": "Senior Software Engineer",
        "hostedUrl": "https://jobs.lever.co/x/abc",
        "createdAt": 1765000000000,
        "categories": {"location": "New York City"},
        "descriptionPlain": "Build infra",
        "lists": [{"text": "Reqs", "content": "<li>Python</li>"}],
    }
    job = lever.parse_job(raw, "Plaid")
    assert job.location == "New York City"
    assert "Build infra" in job.description and "Python" in job.description
    assert job.posted_at is not None


def test_ashby_parse():
    raw = {
        "id": "j1",
        "title": "Senior Software Engineer, Backend",
        "location": "New York",
        "secondaryLocations": [{"location": "Remote - US"}],
        "jobUrl": "https://jobs.ashbyhq.com/ramp/j1",
        "publishedAt": "2026-06-09T00:00:00Z",
        "descriptionHtml": "<p>Fintech backend</p>",
    }
    job = ashby.parse_job(raw, "Ramp")
    assert "New York" in job.location and "Remote - US" in job.location
    assert job.description == "Fintech backend"


def test_workday_parse():
    company = Company(
        name="NVIDIA", ats="workday",
        params={"tenant": "nvidia", "host": "nvidia.wd5.myworkdayjobs.com", "site": "NVIDIAExternalCareerSite"},
    )
    raw = {
        "title": "Senior Software Engineer",
        "externalPath": "/job/US-NY-New-York/Senior-Software-Engineer_JR123",
        "locationsText": "New York, NY",
        "postedOn": "Posted 2 Days Ago",
        "bulletFields": ["JR123"],
    }
    job = workday.parse_job(raw, company)
    assert job.job_id == "Senior-Software-Engineer_JR123"
    assert "nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/" in job.url
    assert job.posted_at is not None
