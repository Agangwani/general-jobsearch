from pathlib import Path

import yaml

from jobsearch.filters import JobFilter
from jobsearch.models import JobPosting

SETTINGS = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())
FILTER = JobFilter(SETTINGS["search"])


def job(title, location="New York, NY"):
    return JobPosting(company="X", title=title, location=location, url="", job_id="1")


def test_senior_swe_titles_pass():
    assert FILTER.matches(job("Senior Software Engineer"))
    assert FILTER.matches(job("Senior Backend Engineer, Payments"))
    assert FILTER.matches(job("Staff Software Engineer - Platform"))
    assert FILTER.matches(job("Software Engineer III"))
    assert FILTER.matches(job("Senior Software Engineer, Distributed Systems"))


def test_unwanted_titles_fail():
    assert not FILTER.matches(job("Software Engineering Intern"))
    assert not FILTER.matches(job("Engineering Manager, Fraud"))
    assert not FILTER.matches(job("Principal Software Engineer"))
    assert not FILTER.matches(job("Senior iOS Engineer"))
    assert not FILTER.matches(job("Senior Product Designer"))
    assert not FILTER.matches(job("Junior Software Engineer"))


def test_location_filtering():
    assert FILTER.matches(job("Senior Software Engineer", "New York, NY, United States"))
    assert FILTER.matches(job("Senior Software Engineer", "NYC HQ"))
    assert FILTER.matches(job("Senior Software Engineer", "Brooklyn, New York"))
    assert not FILTER.matches(job("Senior Software Engineer", "San Francisco, CA"))
    assert not FILTER.matches(job("Senior Software Engineer", "Remote - US"))  # include_remote: false
