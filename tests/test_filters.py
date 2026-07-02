from pathlib import Path

import yaml

from jobsearch.filters import (
    MATCH, NEAR_LOCATION, NEAR_TITLE, OUT, JobFilter, build_funnel, extract_max_pay,
)
from jobsearch.models import JobPosting
from jobsearch.pipeline import (
    _profile_is_engineering, append_startup_titles, apply_startup_search_knobs,
)

SETTINGS = yaml.safe_load((Path(__file__).parent.parent / "config" / "settings.yaml").read_text())
FILTER = JobFilter(SETTINGS["search"])
# The same search config with the 2026-06-12 policy carve-outs switched off,
# for testing the strict behavior in isolation.
STRICT = JobFilter({**SETTINGS["search"], "remote_min_pay": 0, "promote_unleveled": False})


def job(title, location="New York, NY", description=""):
    return JobPosting(company="X", title=title, location=location, url="", job_id="1",
                      description=description)


def test_startup_relaxation_admits_flat_titles_and_remote():
    """The startup-track knobs (from settings.yaml startups:) admit the flatter
    titles and remote roles that the strict main filter buries in near-miss."""
    cfg = SETTINGS["startups"]
    settings = {"search": dict(SETTINGS["search"]), "ranking": dict(SETTINGS["ranking"])}
    apply_startup_search_knobs(settings, cfg)
    added = append_startup_titles(settings, cfg)

    assert added == len(cfg["extra_title_include"])
    assert settings["search"]["include_remote"] is True
    assert settings["search"]["remote_min_pay"] == 0
    assert settings["ranking"]["max_age_days"] == 90

    relaxed = JobFilter(settings["search"])
    remote_founding = job("Founding Engineer", location="Remote - US")
    ml_nyc = job("Machine Learning Engineer", location="New York, NY")
    # Both are matches under the relaxed startup filter...
    assert relaxed.classify(remote_founding)[0] == MATCH
    assert relaxed.classify(ml_nyc)[0] == MATCH
    # ...but the strict main filter does NOT match the remote founding role
    # (fails-before evidence that the relaxation is what admits it).
    assert FILTER.classify(remote_founding)[0] != MATCH


class _Profile:
    def __init__(self, occupations):
        self.occupations = occupations


def test_profile_is_engineering_gates_startup_titles():
    # None (manual/low-confidence) -> True (settings default to SWE patterns).
    assert _profile_is_engineering(None) is True
    assert _profile_is_engineering(_Profile(["Software Engineer", "Data Engineer"]))
    assert _profile_is_engineering(_Profile(["Machine Learning Engineer"]))
    # A non-engineering resume must NOT get software-engineer titles grafted in.
    assert not _profile_is_engineering(_Profile(["Customer Success Manager"]))
    assert not _profile_is_engineering(_Profile(["Registered Nurse"]))


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


def test_classify_unleveled_title_strict():
    # Stripe-style: no level in the title, seniority only in the description.
    status, reason = STRICT.classify(
        job("Backend Engineer, Payments", description="We require 6+ years of experience.")
    )
    assert status == NEAR_TITLE
    assert reason == "UNLEVELED_TITLE"


def test_unleveled_title_promoted():
    # Policy 2026-06-12: unleveled software titles with 5+ years required are
    # promoted into the main table.
    assert FILTER.classify(
        job("Backend Engineer, Payments", description="We require 6+ years of experience.")
    ) == (MATCH, "")
    # ...but only software-looking titles; other engineering stays near-miss.
    status, reason = FILTER.classify(
        job("Network Engineer", description="8+ years of experience."))
    assert status == NEAR_TITLE


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


def test_classify_remote_only_strict():
    status, reason = STRICT.classify(job("Senior Software Engineer", "Remote - US"))
    assert status == NEAR_LOCATION
    assert reason == "REMOTE_ONLY"


def test_remote_pay_carveout():
    # Policy 2026-06-12: remote-US enters the main table only with a posted
    # pay range topping out at/above $200k.
    rich = "Base salary range: $180,000 - $230,000 plus equity."
    poor = "Base salary range: $130,000 - $170,000."
    assert FILTER.classify(
        job("Senior Software Engineer", "Remote - US", rich)) == (MATCH, "")
    assert FILTER.classify(
        job("Senior Software Engineer", "Remote - US", poor)) == (
        NEAR_LOCATION, "REMOTE_PAY_BELOW_MIN")
    assert FILTER.classify(
        job("Senior Software Engineer", "Remote - US", "Great benefits!")) == (
        NEAR_LOCATION, "REMOTE_NO_PAY_RANGE")
    # the carve-out also lets remote near-titles into near-miss
    status, reason = FILTER.classify(
        job("Software Engineer II", "Remote - US", rich))
    assert (status, reason) == (NEAR_TITLE, "MID_LEVEL")
    # ...but unleveled + remote + pay → fully promoted
    assert FILTER.classify(
        job("Software Engineer, Infrastructure", "Remote - US",
            rich + " 7+ years of experience.")) == (MATCH, "")


def test_extract_max_pay():
    assert extract_max_pay("range of $187,500 to $245,000 annually") == 245000
    assert extract_max_pay("pay: $180K–$220K + equity") == 220000
    assert extract_max_pay("$172.5K max") == 172500
    assert extract_max_pay("about $210000 per year") == 210000
    assert extract_max_pay("earn $45/hour") is None       # not an annual salary
    assert extract_max_pay("save $500 on day one") is None
    assert extract_max_pay("no numbers here") is None
    assert extract_max_pay("") is None


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
    funnel = build_funnel(jobs, STRICT)
    row = funnel["X"]
    assert row["fetched"] == 4
    assert row["title_pass"] == 2
    assert row["loc_pass"] == 3
    assert row["matched"] == 1
    assert row["near_miss"] == 1
    # under the live policy the unleveled backend role is promoted
    assert build_funnel(jobs, FILTER)["X"]["matched"] == 2


def test_build_funnel_aged_out():
    from datetime import datetime, timedelta, timezone
    old = job("Senior Software Engineer")
    old.posted_at = datetime.now(timezone.utc) - timedelta(days=90)
    fresh = job("Senior Software Engineer")
    funnel = build_funnel([old, fresh], FILTER, max_age_days=45)
    row = funnel["X"]
    assert row["matched"] == 1
    assert row["aged_out"] == 1
