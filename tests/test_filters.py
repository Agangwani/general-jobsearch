from pathlib import Path

import yaml

from jobsearch.filters import MATCH, NEAR_LOCATION, NEAR_TITLE, OUT, JobFilter, build_funnel
from jobsearch.models import JobPosting

SETTINGS = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())
FILTER = JobFilter(SETTINGS["search"])


def job(title, location="New York, NY", description=""):
    return JobPosting(company="X", title=title, location=location, url="", job_id="1",
                      description=description)


def test_senior_swe_titles_pass():
    assert FILTER.matches(job("Senior Software Engineer"))
    assert FILTER.matches(job("Senior Backend Engineer, Payments"))
    assert FILTER.matches(job("Staff Software Engineer - Platform"))
    assert FILTER.matches(job("Software Engineer III"))
    assert FILTER.matches(job("Senior Software Engineer, Distributed Systems"))


def test_sr_abbreviation_passes():
    # Pinterest-style titles; previously a guaranteed false zero.
    assert FILTER.matches(job("Sr. Software Engineer"))
    assert FILTER.matches(job("Sr Software Engineer, Core Product"))
    assert FILTER.matches(job("Sr. Backend Engineer"))


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


def test_classify_match():
    assert FILTER.classify(job("Senior Software Engineer")) == (MATCH, "")


def test_classify_unleveled_title():
    # Stripe-style: no level in the title, seniority only in the description.
    status, reason = FILTER.classify(
        job("Backend Engineer, Payments", description="We require 6+ years of experience.")
    )
    assert status == NEAR_TITLE
    assert reason == "UNLEVELED_TITLE"


def test_classify_unleveled_unverified():
    status, reason = FILTER.classify(job("Backend Engineer, Payments", description="Build APIs."))
    assert status == NEAR_TITLE
    assert reason == "UNLEVELED_TITLE_UNVERIFIED"


def test_classify_other_eng_track():
    status, reason = FILTER.classify(job("Senior Site Reliability Engineer"))
    assert status == NEAR_TITLE
    assert reason == "OTHER_ENG_TRACK"


def test_classify_excluded_track():
    status, reason = FILTER.classify(job("Senior iOS Engineer"))
    assert status == NEAR_TITLE
    assert reason.startswith("EXCLUDED_TRACK:")


def test_classify_remote_only():
    status, reason = FILTER.classify(job("Senior Software Engineer", "Remote - US"))
    assert status == NEAR_LOCATION
    assert reason == "REMOTE_ONLY"


def test_classify_out():
    assert FILTER.classify(job("Software Engineering Intern"))[0] == OUT
    assert FILTER.classify(job("Engineering Manager"))[0] == OUT
    assert FILTER.classify(job("Senior Software Engineer", "London, UK"))[0] == OUT
    assert FILTER.classify(job("Account Executive"))[0] == OUT


def test_build_funnel():
    jobs = [
        job("Senior Software Engineer"),                                    # match
        job("Backend Engineer", description="7+ years required"),          # near-miss
        job("Senior Software Engineer", "San Francisco, CA"),              # out (title ok)
        job("Account Executive"),                                          # out
    ]
    funnel = build_funnel(jobs, FILTER)
    row = funnel["X"]
    assert row["fetched"] == 4
    assert row["title_pass"] == 2
    assert row["loc_pass"] == 3
    assert row["matched"] == 1
    assert row["near_miss"] == 1


def test_build_funnel_aged_out():
    from datetime import datetime, timedelta, timezone
    old = job("Senior Software Engineer")
    old.posted_at = datetime.now(timezone.utc) - timedelta(days=90)
    fresh = job("Senior Software Engineer")
    funnel = build_funnel([old, fresh], FILTER, max_age_days=45)
    row = funnel["X"]
    assert row["matched"] == 1
    assert row["aged_out"] == 1
