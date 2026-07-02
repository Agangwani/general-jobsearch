"""Dynamic company discovery: lead merging, resume-relevance ranking,
category inference, registry emission, and load-time merging — all offline."""

import yaml

from jobsearch.company_discovery import (
    emit_registry,
    filter_known,
    filter_oversized,
    hosted_board_url,
    infer_categories,
    merge_leads,
    rank_leads,
)
from jobsearch.config import load_companies, load_registry, load_settings
from jobsearch.models import CompanyLead
from jobsearch.utils import normalize_company_name


def test_normalize_company_name():
    assert normalize_company_name("Datadog, Inc.") == "datadog"
    assert normalize_company_name("datadog") == "datadog"
    assert normalize_company_name("The Trade Desk") == "trade desk"
    assert normalize_company_name("D.E. Shaw & Co") == "d e shaw"
    assert normalize_company_name("Warby Parker LLC") == "warby parker"
    assert normalize_company_name("") == ""


def test_merge_leads_collapses_across_sources():
    leads = [
        CompanyLead(name="Ramp", sources=["hn_hiring"],
                    titles=["Senior Backend Engineer"],
                    urls=["https://jobs.ashbyhq.com/ramp"]),
        CompanyLead(name="Ramp, Inc.", sources=["themuse"],
                    titles=["Senior Backend Engineer", "Staff Engineer"],
                    locations=["New York, NY"]),
        CompanyLead(name="Figma", sources=["themuse"], titles=["Product Designer"]),
    ]
    merged = {lead.name: lead for lead in merge_leads(leads)}
    assert set(merged) == {"Ramp", "Figma"}  # first-seen spelling wins
    ramp = merged["Ramp"]
    assert ramp.mentions == 2
    assert sorted(ramp.sources) == ["hn_hiring", "themuse"]
    assert ramp.titles == ["Senior Backend Engineer", "Staff Engineer"]  # deduped
    assert ramp.urls == ["https://jobs.ashbyhq.com/ramp"]


def test_filter_known_drops_registry_and_excluded():
    leads = [CompanyLead(name="Stripe"), CompanyLead(name="Capital One, Inc."),
             CompanyLead(name="NewCo")]
    fresh = filter_known(leads, known={"stripe"}, exclude={"capital one"})
    assert [lead.name for lead in fresh] == ["NewCo"]


def test_filter_oversized_drops_known_enterprises_keeps_unknown_size():
    leads = [
        CompanyLead(name="BigBank", meta={"employees": "50000"}),
        CompanyLead(name="Scaleup", meta={"employees": "51-200"}),
        CompanyLead(name="MuseCo"),  # themuse: no headcount -> never dropped
    ]
    kept, dropped = filter_oversized(leads, max_employees=2000)
    assert [lead.name for lead in kept] == ["Scaleup", "MuseCo"]
    assert [lead.name for lead in dropped] == ["BigBank"]
    # A zero/negative ceiling disables the guard entirely.
    kept_all, dropped_none = filter_oversized(leads, max_employees=0)
    assert len(kept_all) == 3 and dropped_none == []


def test_rank_leads_prefers_resume_relevant_evidence():
    resume = ("Senior software engineer: distributed systems, Python, Kafka, "
              "payments infrastructure, backend APIs, PostgreSQL.")
    leads = [
        CompanyLead(name="PayCo", titles=["Senior Software Engineer, Payments"],
                    snippets=["Distributed payments infrastructure in Python and Kafka."]),
        CompanyLead(name="MakeupCo", titles=["Retail Makeup Artist"],
                    snippets=["Cosmetics counter sales and beauty consultations."]),
    ]
    ranked = rank_leads(leads, resume)
    assert [lead.name for lead in ranked] == ["PayCo", "MakeupCo"]
    assert ranked[0].relevance == 100.0
    assert ranked[1].relevance < ranked[0].relevance


def test_rank_leads_mentions_break_evidence_free_ties():
    leads = [CompanyLead(name="Quiet", mentions=1),
             CompanyLead(name="Busy", mentions=5)]
    ranked = rank_leads(leads, "software engineer resume text")
    assert ranked[0].name == "Busy"  # no textual signal → most-mentioned first


def test_infer_categories_swe_resume():
    keywords = ["software engineer", "distributed systems", "python", "kafka",
                "backend", "kubernetes", "apis"]
    assert infer_categories(keywords, "senior software engineer") == [
        "Software Engineering"]


def test_infer_categories_data_science_resume():
    keywords = ["machine learning", "pytorch", "models", "nlp", "python",
                "data scientist", "statistics"]
    categories = infer_categories(keywords, "machine learning engineer")
    assert categories[0] == "Data Science"


def test_infer_categories_defaults_when_nothing_matches():
    assert infer_categories([], "") == ["Software Engineering"]


def test_hosted_board_url():
    assert hosted_board_url({"ats": "greenhouse", "board": "acme"}) == \
        "https://job-boards.greenhouse.io/acme"
    assert hosted_board_url({"ats": "lever", "org": "acme"}) == "https://jobs.lever.co/acme"
    assert hosted_board_url({"ats": "workday", "tenant": "acme",
                             "host": "acme.wd5.myworkdayjobs.com", "site": "External"}) == \
        "https://acme.wd5.myworkdayjobs.com/External"
    assert hosted_board_url({"ats": "amazon"}) == ""


def test_emit_registry_round_trips_through_load_companies(tmp_path):
    resolved = [
        (CompanyLead(name="Ramp", sources=["hn_hiring", "themuse"], mentions=3),
         {"ats": "ashby", "org": "ramp", "_postings": 12}, "url"),
    ]
    unresolved = [CompanyLead(name="Mystery Startup", sources=["hn_hiring"],
                              urls=["https://mystery.example/careers"], mentions=1)]
    text = emit_registry(resolved, unresolved)
    path = tmp_path / "companies.discovered.yaml"
    path.write_text(text)

    companies, manual = load_companies(path)
    assert len(companies) == 1
    ramp = companies[0]
    assert (ramp.name, ramp.ats, ramp.tags) == ("Ramp", "ashby", ["discovered"])
    assert ramp.careers_url == "https://jobs.ashbyhq.com/ramp"
    assert ramp.params == {"org": "ramp"}  # discovered_via/_postings must not leak
    assert manual[0]["name"] == "Mystery Startup"
    assert manual[0]["careers_url"] == "https://mystery.example/careers"
    # audit trail survives in the raw yaml
    raw = yaml.safe_load(text)
    assert raw["companies"][0]["discovered_via"] == "hn_hiring+themuse (url)"


def _write_minimal_config(root, discovered: str | None):
    (root / "config").mkdir()
    (root / "config" / "companies.yaml").write_text(
        "companies:\n"
        "  - name: Stripe\n    ats: greenhouse\n    board: stripe\n"
        "manual_check:\n"
        "  - name: LinkedIn\n    careers_url: https://careers.linkedin.com\n"
    )
    (root / "config" / "settings.yaml").write_text(
        "discovery:\n"
        "  exclude_companies: [Capital One]\n"
        "  output_file: data/companies.discovered.yaml\n"
    )
    if discovered is not None:
        (root / "data").mkdir()
        (root / "data" / "companies.discovered.yaml").write_text(discovered)


def test_load_registry_without_discovered_file(tmp_path):
    _write_minimal_config(tmp_path, discovered=None)
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    companies, manual = load_registry(tmp_path, settings)
    assert [c.name for c in companies] == ["Stripe"]
    assert [m["name"] for m in manual] == ["LinkedIn"]


def test_load_registry_merges_curated_wins_and_excludes(tmp_path):
    discovered = (
        "companies:\n"
        "  - name: Stripe, Inc.\n    ats: lever\n    org: wrong\n"   # curated wins
        "  - name: Capital One\n    ats: greenhouse\n    board: capitalone\n"  # excluded
        "  - name: Ramp\n    ats: ashby\n    org: ramp\n"
        "    tags: [discovered]\n    discovered_via: hn_hiring (url)\n"
        "manual_check:\n"
        "  - name: LinkedIn\n    careers_url: https://dupe\n"        # already manual
        "  - name: Mystery Startup\n    careers_url: ''\n"
    )
    _write_minimal_config(tmp_path, discovered=discovered)
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    companies, manual = load_registry(tmp_path, settings)

    assert [c.name for c in companies] == ["Stripe", "Ramp"]
    assert companies[0].ats == "greenhouse"  # the curated Stripe, not the discovered one
    assert [m["name"] for m in manual] == ["LinkedIn", "Mystery Startup"]
    assert manual[0]["careers_url"] == "https://careers.linkedin.com"
