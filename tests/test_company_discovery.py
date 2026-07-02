"""Dynamic company discovery: lead merging, resume-relevance ranking,
category inference, registry emission, and load-time merging — all offline."""

import yaml

import jobsearch.company_discovery as company_discovery
from jobsearch.company_discovery import (
    emit_registry,
    filter_funding,
    filter_known,
    filter_oversized,
    _registry_company_count,
    hosted_board_url,
    infer_categories,
    maybe_run_discovery,
    merge_leads,
    rank_leads,
)
from jobsearch.config import load_companies, load_registry, load_settings
from jobsearch.models import CompanyLead
from jobsearch.tracks import build_track
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


def test_filter_funding_drops_overfunded_falls_back_to_last_round_keeps_unknown():
    leads = [
        CompanyLead(name="LateStage", meta={"total_raised": "$800M"}),   # dropped
        CompanyLead(name="MidRound", meta={"last_round_amount": "$20M"}),  # kept (fallback)
        CompanyLead(name="NoFunding"),                                    # kept (unknown)
    ]
    kept, dropped = filter_funding(leads, max_raised=500_000_000)
    assert [lead.name for lead in kept] == ["MidRound", "NoFunding"]
    assert [lead.name for lead in dropped] == ["LateStage"]
    # A zero/negative ceiling disables the guard entirely.
    kept_all, dropped_none = filter_funding(leads, max_raised=0)
    assert len(kept_all) == 3 and dropped_none == []


def test_filter_funding_falls_back_when_total_raised_is_unparseable():
    # A truthy-but-unparseable total_raised ("Undisclosed") must not mask a real
    # last_round_amount that exceeds the ceiling.
    over = CompanyLead(name="Over", meta={"total_raised": "Undisclosed",
                                          "last_round_amount": "$300M"})
    # A parseable total_raised under the ceiling wins and is NOT overridden by a
    # larger last_round_amount.
    under = CompanyLead(name="Under", meta={"total_raised": "$10M",
                                            "last_round_amount": "$999M"})
    unknown = CompanyLead(name="Unknown", meta={"total_raised": "N/A"})
    kept, dropped = filter_funding([over, under, unknown], max_raised=50_000_000)
    assert [l.name for l in dropped] == ["Over"]
    assert [l.name for l in kept] == ["Under", "Unknown"]


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


# -------------------------------------------- discovery-on-run (Stage 3) ---
def _main_track(tmp_path, **discovery):
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    settings["discovery"] = {"output_file": "data/companies.discovered.yaml",
                             **discovery}
    return settings, build_track(tmp_path, settings, "main")


def test_maybe_run_discovery_off_by_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(company_discovery, "discover_companies",
                        lambda *a, **k: calls.append(a) or 0)
    settings, track = _main_track(tmp_path)                 # no on_run key
    assert maybe_run_discovery(tmp_path, settings, track) is False
    assert calls == []                                     # never touched the network


def test_maybe_run_discovery_runs_when_enabled(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(company_discovery, "discover_companies",
                        lambda root, track_name="main", user_id="local": calls.append(track_name) or 0)
    settings, track = _main_track(tmp_path, on_run=True)
    assert maybe_run_discovery(tmp_path, settings, track) is True
    assert calls == ["main"]


def test_maybe_run_discovery_throttled_by_interval(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(company_discovery, "discover_companies",
                        lambda *a, **k: calls.append(a) or 0)
    settings, track = _main_track(tmp_path, on_run=True, min_interval_minutes=5)
    track.registry_file.parent.mkdir(parents=True, exist_ok=True)
    track.registry_file.write_text("companies: []\n")
    mtime = track.registry_file.stat().st_mtime
    # Regenerated 1 min ago (< 5) → skipped; 10 min ago (> 5) → runs.
    assert maybe_run_discovery(tmp_path, settings, track, now=mtime + 60) is False
    assert calls == []
    assert maybe_run_discovery(tmp_path, settings, track, now=mtime + 600) is True
    assert calls == [(tmp_path,)]


def test_maybe_run_discovery_interval_absent_registry_runs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(company_discovery, "discover_companies",
                        lambda *a, **k: calls.append(a) or 0)
    settings, track = _main_track(tmp_path, on_run=True, min_interval_minutes=60)
    assert not track.registry_file.exists()               # nothing generated yet
    assert maybe_run_discovery(tmp_path, settings, track) is True


def test_maybe_run_discovery_failure_does_not_raise(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("aggregator down")
    monkeypatch.setattr(company_discovery, "discover_companies", boom)
    settings, track = _main_track(tmp_path, on_run=True)
    # Best-effort: a discovery failure is swallowed so the run proceeds.
    assert maybe_run_discovery(tmp_path, settings, track) is False


def _registry_yaml(n):
    return yaml.safe_dump({"companies": [
        {"name": f"Co{i}", "ats": "greenhouse", "board": f"co{i}"} for i in range(n)]})


def test_maybe_run_discovery_rejects_degraded_refresh(tmp_path, monkeypatch):
    """A partial source outage that shrinks the registry must not replace a
    healthy one — the prior content AND mtime are restored so the next run
    retries instead of locking a degraded set behind the throttle."""
    import os
    settings, track = _main_track(tmp_path, on_run=True)
    track.registry_file.parent.mkdir(parents=True, exist_ok=True)
    track.registry_file.write_text(_registry_yaml(20))               # healthy prior
    os.utime(track.registry_file, (1_000_000, 1_000_000))            # a known old mtime
    prior_mtime = track.registry_file.stat().st_mtime

    monkeypatch.setattr(company_discovery, "discover_companies",
        lambda root, track_name="main", user_id="local": track.registry_file.write_text(_registry_yaml(2)) or 0)
    assert maybe_run_discovery(tmp_path, settings, track) is False   # rejected
    assert _registry_company_count(track.registry_file.read_text()) == 20   # prior kept
    assert track.registry_file.stat().st_mtime == prior_mtime       # mtime restored → retry


def test_maybe_run_discovery_accepts_healthy_refresh(tmp_path, monkeypatch):
    settings, track = _main_track(tmp_path, on_run=True)
    track.registry_file.parent.mkdir(parents=True, exist_ok=True)
    track.registry_file.write_text(_registry_yaml(20))
    monkeypatch.setattr(company_discovery, "discover_companies",
        lambda root, track_name="main", user_id="local": track.registry_file.write_text(_registry_yaml(18)) or 0)
    assert maybe_run_discovery(tmp_path, settings, track) is True    # >= 50% of prior
    assert _registry_company_count(track.registry_file.read_text()) == 18


def test_maybe_run_discovery_accepts_when_no_prior(tmp_path, monkeypatch):
    settings, track = _main_track(tmp_path, on_run=True)             # nothing to protect
    def _write(root, track_name="main", user_id="local"):
        track.registry_file.parent.mkdir(parents=True, exist_ok=True)
        track.registry_file.write_text(_registry_yaml(3))
        return 0
    monkeypatch.setattr(company_discovery, "discover_companies", _write)
    assert maybe_run_discovery(tmp_path, settings, track) is True
    assert _registry_company_count(track.registry_file.read_text()) == 3
