"""Resume → role-profile matching: occupation matching (TF-IDF backend),
seniority inference, title-filter generation, and the end-to-end fix for the
'non-SWE resume yields SWE jobs' bug. All offline (TF-IDF backend; MiniLM is
exercised only if the optional package is present)."""

from pathlib import Path

import pytest

from jobsearch.filters import JobFilter
from jobsearch.models import JobPosting
from jobsearch.role_profile import (
    apply_profile,
    build_profile,
    build_title_filters,
    infer_seniority,
    load_occupations,
    match_occupations,
    resolve_profile,
)

OCC_PATH = Path(__file__).resolve().parent.parent / "config" / "occupations.yaml"
OCCUPATIONS = load_occupations(OCC_PATH)

# The resume from the bug report (Gita Gangwani — Customer Success / consulting),
# condensed to the load-bearing vocabulary.
CS_RESUME = """Senior Customer Success Specialist. Over 20 years for clients in the
EdTech space, cloud, digital transformation, API management. Established Agile
Project Manager migrating enterprise applications to Scrum. JIRA. Consulting led
deals. Trusted advisor relationships. Transformation roadmaps. Business cases.
Stakeholder management. Customer design thinking. Director. Cloud strategy and
architecture. Cloud governance. Market research. Thought leadership."""

SWE_RESUME = """Senior Software Engineer. Distributed systems, backend services in
Python and Go. Kubernetes, microservices, REST APIs, PostgreSQL, Kafka. Designed
scalable infrastructure. System design. Led backend platform work."""


def test_occupation_seed_loads():
    assert len(OCCUPATIONS) >= 15
    names = {occ.name for occ in OCCUPATIONS}
    assert {"Software Engineer", "Customer Success Manager", "Project Manager"} <= names


def test_cs_resume_matches_customer_facing_not_swe():
    ranked, used = match_occupations(CS_RESUME, OCCUPATIONS, backend="tfidf")
    assert used == "tfidf"
    top = ranked[0][0].name
    # The right answer is a customer-success / consulting / PM role — never SWE.
    assert top in {"Customer Success Manager", "Management Consultant",
                   "Project Manager", "Technical Program Manager",
                   "Cloud / Solutions Architect"}
    assert ranked[0][0].name != "Software Engineer"


def test_swe_resume_still_matches_software_engineer():
    ranked, _ = match_occupations(SWE_RESUME, OCCUPATIONS, backend="tfidf")
    assert ranked[0][0].name == "Software Engineer"


def test_infer_seniority():
    assert infer_seniority(CS_RESUME) == "leadership"   # "Director" + 20 years
    assert infer_seniority(SWE_RESUME) == "senior"      # "Senior" in the header
    assert infer_seniority("Software developer, 1 year of experience") == "junior"
    assert infer_seniority("Engineer with 5 years building web apps") == "mid"


def test_build_title_filters_seniority_aware_excludes():
    cs = next(o for o in OCCUPATIONS if o.name == "Customer Success Manager")
    # Leadership profile: management titles must NOT be excluded.
    _, exclude = build_title_filters([cs], "leadership")
    joined = " ".join(exclude)
    assert "intern" in joined
    assert "manager" not in joined and "director" not in joined
    # Junior IC profile for an IC occupation: management titles excluded.
    swe = next(o for o in OCCUPATIONS if o.name == "Software Engineer")
    _, exclude_junior = build_title_filters([swe], "junior")
    assert "manager" in " ".join(exclude_junior)


def test_profile_filter_admits_the_right_roles_for_cs_resume():
    """The end-to-end fix: with the CS resume's generated filters, Customer
    Success / PM roles match and Senior Software Engineer does not — the exact
    inversion of the reported bug."""
    profile = build_profile(CS_RESUME, OCCUPATIONS, backend="tfidf")
    jf = JobFilter(apply_profile({"locations": ["new york"]}, profile))

    def classify(title):
        return jf.classify(JobPosting(company="X", title=title,
                                      location="New York, NY", url="", job_id="1"))[0]

    assert classify("Senior Customer Success Manager") == "match" \
        or classify("Customer Success Manager") == "match" \
        or classify("Senior Project Manager") == "match"
    # The reported bug: a SWE role was a main-table MATCH for this resume. It
    # must no longer be — at most a broadened-search near-miss.
    assert classify("Senior Software Engineer, Backend") != "match"
    assert profile.query != "senior software engineer"
    assert profile.skills  # relevant skills surfaced


def test_profile_blends_close_runner_up():
    profile = build_profile(CS_RESUME, OCCUPATIONS, backend="tfidf")
    assert 1 <= len(profile.occupations) <= 2


def test_resolve_profile_respects_manual_and_threshold(tmp_path):
    settings = {"search": {"role_targeting": "auto"},
                "role": {"occupations_file": str(OCC_PATH)}}
    assert resolve_profile(Path("/"), settings, SWE_RESUME) is not None

    manual = {"search": {"role_targeting": "manual"}, "role": {}}
    assert resolve_profile(Path("/"), manual, SWE_RESUME) is None

    strict = {"search": {"role_targeting": "auto", "role_match_min_score": 0.99},
              "role": {"occupations_file": str(OCC_PATH)}}
    assert resolve_profile(Path("/"), strict, SWE_RESUME) is None  # nothing scores that high


def test_apply_profile_preserves_location_knobs():
    profile = build_profile(SWE_RESUME, OCCUPATIONS, backend="tfidf")
    before = {"locations": ["new york"], "remote_min_pay": 200000, "query": "old"}
    after = apply_profile(before, profile)
    assert after["locations"] == ["new york"]
    assert after["remote_min_pay"] == 200000
    assert after["query"] == profile.query and after["query"] != "old"


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("sentence_transformers") is None,
    reason="sentence-transformers not installed (MiniLM backend optional)")
def test_minilm_backend_when_available():
    ranked, used = match_occupations(SWE_RESUME, OCCUPATIONS, backend="minilm")
    # Either MiniLM loaded (used == minilm) or it fell back cleanly to tfidf.
    assert used in {"minilm", "tfidf"}
    assert ranked[0][0].name == "Software Engineer"
