"""Comprehensive, multi-industry test suite driven by 20 real-world-style resumes
(one per top NYC industry — see tests/industry_fixtures.py and
tests/fixtures/resumes/).

It proves the two properties the product promises:

1. **The whole flow tailors to the resume.** Role targeting, title filters,
   company discovery, and fit scoring all re-target per resume — a nurse's run
   is not a software engineer's run.
2. **No homogeneity.** Different resumes do NOT surface the same companies or the
   same job postings; each industry's run leads with that industry's companies
   and roles.

The one deliberate exception is **prep**: the curriculum is universal (every
track is available to everyone), and the Behavioral track is recommended for
*every* resume — while discipline-specific tracks are highlighted per resume.

All offline (TF-IDF backend; deterministic).
"""

from collections import Counter
from pathlib import Path

import pytest

from jobsearch.company_discovery import infer_categories, rank_leads
from jobsearch.filters import MATCH, JobFilter
from jobsearch.models import CompanyLead, JobPosting
from jobsearch.resume import extract_keywords
from jobsearch.role_profile import apply_profile, build_profile, infer_seniority, load_occupations
from jobsearch.scoring import apply_recency, rank_companies, score_jobs

from tests.industry_fixtures import FIXTURES

OCC_PATH = Path(__file__).resolve().parent.parent / "config" / "occupations.yaml"
OCCUPATIONS = load_occupations(OCC_PATH)
IDS = [f.slug for f in FIXTURES]

VALID_SENIORITY = {"junior", "mid", "senior", "leadership"}


def _profile(fixture):
    return build_profile(fixture.resume_text(), OCCUPATIONS, backend="tfidf")


def _all_leads():
    """A fresh pool of one CompanyLead per industry (rank_leads mutates/sorts)."""
    return [
        CompanyLead(name=f.company, titles=list(f.company_titles),
                    snippets=[f.company_snippet], mentions=2)
        for f in FIXTURES
    ]


def _all_jobs():
    """A fresh shared corpus of one posting per industry, all in NYC."""
    return [
        JobPosting(company=f.company, title=f.job_title, location="New York, NY",
                   url="https://example.com/" + f.slug, job_id=f.slug,
                   description=f.job_description, source="test")
        for f in FIXTURES
    ]


# ----------------------------------------------------------------- fixtures sanity

def test_twenty_industries_each_with_a_resume():
    assert len(FIXTURES) == 20
    for f in FIXTURES:
        assert f.path.exists(), f"missing resume file: {f.resume_file}"
        assert len(f.resume_text()) > 300, f"resume too short: {f.slug}"


# --------------------------------------------------------------- resume intake

@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_keywords_extracted_per_resume(fixture):
    """Resume intake works for every industry — extraction yields real, domain
    keywords (garbled extraction would surface as junk/empty)."""
    keywords = extract_keywords(fixture.resume_text())
    assert len(keywords) >= 5, f"too few keywords for {fixture.slug}: {keywords}"


# ----------------------------------------------------------- role targeting

@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_role_targeting_matches_expected_occupation(fixture):
    """Each resume is matched to its industry's occupation — the core 'the flow
    targets the roles the resume is actually for' guarantee."""
    profile = _profile(fixture)
    assert profile.occupations[0] == fixture.expected_occupation, (
        f"{fixture.slug}: matched {profile.occupations[0]!r}, "
        f"expected {fixture.expected_occupation!r}")
    assert profile.skills, f"{fixture.slug}: no relevant skills surfaced"
    assert infer_seniority(fixture.resume_text()) in VALID_SENIORITY


def test_software_engineer_targeted_only_by_the_tech_resume():
    """The original bug, generalized: a non-software resume must never come back
    targeting Software Engineer; the tech resume must."""
    for fixture in FIXTURES:
        top = _profile(fixture).occupations[0]
        if fixture.slug == "technology":
            assert top == "Software Engineer"
        else:
            assert top != "Software Engineer", f"{fixture.slug} mis-targeted as SWE"


def test_every_resume_targets_a_distinct_occupation():
    """20 industries resolve to 20 distinct occupations — the taxonomy is not
    collapsing different industries onto one role."""
    tops = [_profile(f).occupations[0] for f in FIXTURES]
    assert len(set(tops)) == 20, f"occupations not distinct: {Counter(tops)}"


# --------------------------------------------------------- title filters tailor

@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_title_filters_are_tailored(fixture):
    """The generated title filter admits the resume's own role and (for every
    non-software resume) rejects 'Senior Software Engineer' — proving filters
    differ per resume, not a fixed software filter."""
    jf = JobFilter(apply_profile({"locations": ["new york"]}, _profile(fixture)))
    assert jf.title_ok(fixture.own_title), (
        f"{fixture.slug}: own title {fixture.own_title!r} should pass its own filter")
    swe_matches = jf.title_ok("Senior Software Engineer")
    assert swe_matches == (fixture.slug == "technology"), (
        f"{fixture.slug}: 'Senior Software Engineer' title_ok={swe_matches}")


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_category_inference_per_resume(fixture):
    """Company discovery's Muse categories come from the matched occupation, so
    they're populated and non-empty for every resume."""
    profile = _profile(fixture)
    categories = profile.categories or infer_categories(
        extract_keywords(fixture.resume_text()), profile.query)
    assert categories, f"{fixture.slug}: no discovery categories"


# ------------------------------------------------ company discovery: no homogeneity

def test_company_discovery_tailors_and_is_diverse():
    """Different resumes surface different companies. Each industry resume should
    rank its own industry's employer at (or near) the top, and across all 20
    resumes the #1 companies must be diverse — never 'the same companies every
    time'."""
    tops = []
    own_is_top = 0
    for fixture in FIXTURES:
        ranked = rank_leads(_all_leads(), fixture.resume_text())
        tops.append(ranked[0].name)
        if ranked[0].name == fixture.company:
            own_is_top += 1
        assert ranked[0].relevance == 100.0  # best lead scaled to 100

    # The vast majority of resumes lead with their own industry's company.
    assert own_is_top >= 18, f"only {own_is_top}/20 resumes ranked own company #1"
    # High diversity of #1 companies, and no single company dominates.
    assert len(set(tops)) >= 18, f"top companies not diverse: {Counter(tops)}"
    assert max(Counter(tops).values()) <= 3, f"a company dominates: {Counter(tops)}"


def test_company_discovery_is_deterministic():
    """The same resume yields the same ranking twice (so 'different every run'
    only ever reflects new postings, not nondeterminism)."""
    resume = FIXTURES[0].resume_text()
    first = [lead.name for lead in rank_leads(_all_leads(), resume)]
    second = [lead.name for lead in rank_leads(_all_leads(), resume)]
    assert first == second


# ------------------------------------------------- fit scoring: no homogeneity

def test_fit_scoring_tailors_and_is_diverse():
    """Different resumes rank different postings highest. Each resume should put
    its own industry's posting on top, and the top postings across the 20
    resumes must be diverse — never 'the same jobs every time'."""
    tops = []
    own_is_top = 0
    for fixture in FIXTURES:
        jobs = _all_jobs()
        score_jobs(fixture.resume_text(), jobs, clusters=3, corpus=jobs)
        top = max(jobs, key=lambda j: j.fit_score)
        tops.append(top.job_id)
        if top.job_id == fixture.slug:
            own_is_top += 1

    assert own_is_top >= 18, f"only {own_is_top}/20 resumes ranked own job #1"
    assert len(set(tops)) >= 18, f"top jobs not diverse: {Counter(tops)}"
    assert max(Counter(tops).values()) <= 3, f"a job dominates: {Counter(tops)}"


def test_company_fit_ranking_is_industry_appropriate():
    """rank_companies (which sorts the report's company list) puts each resume's
    own-industry employer at the top of the fit ranking."""
    for fixture in FIXTURES:
        jobs = _all_jobs()
        score_jobs(fixture.resume_text(), jobs, clusters=3, corpus=jobs)
        company_fit = rank_companies(jobs, top_n=1)
        best = max(company_fit, key=company_fit.get)
        assert best == fixture.company, (
            f"{fixture.slug}: company fit led with {best!r}, not {fixture.company!r}")


# ------------------------------------------- end-to-end filter + score per resume

@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_end_to_end_filter_admits_own_rejects_foreign(fixture):
    """With the resume's generated filter, its own industry posting is a MATCH
    while a clearly-foreign posting is not — the filter is genuinely re-targeted
    per resume. (All postings share an NYC location, isolating the title test.)"""
    jf = JobFilter(apply_profile({"locations": ["new york"]}, _profile(fixture)))
    jobs = {f.slug: j for f, j in zip(FIXTURES, _all_jobs())}

    own = jobs[fixture.slug]
    assert jf.classify(own)[0] == MATCH, f"{fixture.slug}: own posting not a MATCH"

    # Pick a foreign posting from a clearly different field.
    foreign_slug = "technology" if fixture.slug != "technology" else "healthcare"
    foreign = jobs[foreign_slug]
    assert jf.classify(foreign)[0] != MATCH, (
        f"{fixture.slug}: foreign posting {foreign.title!r} wrongly matched")


def test_pipeline_slice_end_to_end_for_a_non_software_resume():
    """A full scoring+recency+company-ranking slice for the consulting resume,
    mirroring the pipeline, lands on consulting — not engineering."""
    consulting = next(f for f in FIXTURES if f.slug == "consulting")
    jobs = _all_jobs()
    score_jobs(consulting.resume_text(), jobs, clusters=3, corpus=jobs)
    apply_recency(jobs, half_life_days=7, unknown_age_days=14)
    # Best-ranked job is the consulting posting.
    assert jobs[0].job_id == "consulting"
    company_fit = rank_companies(jobs, top_n=1)
    assert max(company_fit, key=company_fit.get) == consulting.company
