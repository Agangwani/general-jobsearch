"""Startup pipeline — pure, offline logic: the YC source parsing, funding /
people extraction, metadata merging, the track abstraction, and the
discover-startups registry + metadata sidecar."""

import json

from jobsearch.company_discovery import enrich_meta, write_meta_sidecar
from jobsearch.config import load_registry, load_settings
from jobsearch.models import CompanyLead
from jobsearch.sources.ycombinator import parse_companies
from jobsearch.startups import (
    extract_funding,
    extract_people,
    find_investors,
    format_money,
    merge_meta,
    parse_money,
)
from jobsearch.tracks import build_track


# --------------------------------------------------------- money parsing ---
def test_parse_money_handles_the_shapes_we_store():
    assert parse_money("$25M") == 25_000_000
    assert parse_money("$1.5 billion") == 1_500_000_000
    assert parse_money("$750k") == 750_000
    assert parse_money("$3,000,000") == 3_000_000
    assert parse_money("1.5B") == 1_500_000_000          # normalized _norm_amount form
    assert parse_money("211967") == 211_967              # bare SEC Form D dollars
    assert parse_money("") is None                       # unknown-is-None contract
    assert parse_money(None) is None
    assert parse_money("Series A") is None               # no figure -> unknown


def test_format_money_compacts():
    assert format_money(211_967) == "$212K"
    assert format_money(6_000_000) == "$6M"
    assert format_money(25_000_000) == "$25M"
    assert format_money(1_500_000_000) == "$1.5B"
    # 3-digit millions/billions must NOT come out as scientific notation
    # (regression: :.2g emitted "$2e+02M" for $200M).
    assert format_money(200_000_000) == "$200M"
    assert format_money(270_000_000) == "$270M"
    assert format_money(160_000_000) == "$160M"
    assert "e" not in format_money(200_000_000)
    assert format_money(2_000_000_000) == "$2B"


# ------------------------------------------------------------- YC source ---
def _yc(name, **kw):
    base = {"name": name, "status": "Active", "all_locations": "New York, NY, USA",
            "isHiring": True}
    base.update(kw)
    return base


def test_yc_parses_metadata_and_filters_by_city():
    records = [
        _yc("Ramp", batch="W19", stage="Series D", team_size=900, industry="Fintech",
            website="https://ramp.com", one_liner="Corporate cards.",
            long_description="Ramp raised $300M Series D backed by Founders Fund.",
            tags=["Fintech"], url="https://ycombinator.com/companies/ramp",
            launched_at=1546300800),
        _yc("BayCo", all_locations="San Francisco, CA, USA", team_size=10),
    ]
    leads = parse_companies(records, ["new york", "nyc"], statuses=["active"])
    assert [lead.name for lead in leads] == ["Ramp"]   # SF company filtered out
    meta = leads[0].meta
    assert meta["employees"] == "900"
    assert meta["batch"] == "W19"
    assert meta["stage"] == "Series D"
    assert meta["founded"] == "2019"
    assert "Y Combinator" in meta["investors"]
    assert "Founders Fund" in meta["investors"]       # mined from the description
    assert meta["last_round_amount"] == "$300M"
    assert meta["website"] == "https://ramp.com"
    assert leads[0].urls == ["https://ramp.com"]       # website → resolution hint


def test_yc_status_and_hiring_filters():
    records = [
        _yc("Live", status="Active", isHiring=True),
        _yc("Dead", status="Inactive", isHiring=True),
        _yc("NotHiring", status="Active", isHiring=False),
    ]
    active = parse_companies(records, [], statuses=["active"])
    assert {lead.name for lead in active} == {"Live", "NotHiring"}
    hiring = parse_companies(records, [], statuses=["active"], require_hiring=True)
    assert {lead.name for lead in hiring} == {"Live"}


# ----------------------------------------------------- funding / people ---
def test_extract_funding_from_blurb():
    f = extract_funding("Seed-stage startup; raised $8M, backed by a16z and Accel.")
    assert f["stage"] == "Seed"
    assert f["last_round_amount"] == "$8M"
    assert f["investors"] == ["Andreessen Horowitz", "Accel"]


def test_extract_funding_series_and_billions():
    f = extract_funding("Announced our Series C of $1.2 billion.")
    assert f["stage"] == "Series C"
    assert f["last_round_amount"] == "$1.2B"


def test_find_investors_canonicalizes_aliases():
    found = find_investors("Investors include a16z, Google Ventures, and USV.")
    assert found == ["Andreessen Horowitz", "GV", "Union Square Ventures"]


def test_extract_people():
    people = extract_people("Founded by Jane Doe. Team of ex-Google and ex-Stripe folks.")
    assert "Founded by Jane Doe" in people
    assert "ex-Google" in people and "ex-Stripe" in people


def test_merge_meta_unions_lists_and_keeps_base_scalars():
    base = {"name": "Ramp", "employees": "900", "investors": ["Y Combinator"]}
    extra = {"employees": "1000", "stage": "Series D",
             "investors": ["Founders Fund"]}
    merged = merge_meta(base, extra)
    assert merged["employees"] == "900"            # base wins scalar
    assert merged["stage"] == "Series D"           # filled from extra
    assert merged["investors"] == ["Y Combinator", "Founders Fund"]  # unioned


# ------------------------------------------------------- discover sidecar ---
def test_enrich_meta_folds_text_funding_into_structured():
    lead = CompanyLead(
        name="Ramp", sources=["ycombinator", "hn_hiring"],
        snippets=["We just closed a Series D, $300M, backed by Thrive Capital."],
        meta={"name": "Ramp", "employees": "900", "investors": ["Y Combinator"],
              "source": "ycombinator"})
    meta = enrich_meta(lead)
    assert meta["employees"] == "900"
    assert meta["stage"] == "Series D"
    assert "Thrive Capital" in meta["investors"]
    assert "Y Combinator" in meta["investors"]


def test_write_meta_sidecar(tmp_path):
    leads = [CompanyLead(name="Ramp, Inc.", sources=["ycombinator"],
                         meta={"name": "Ramp, Inc.", "employees": "900"})]
    path = tmp_path / "startup_meta.json"
    write_meta_sidecar(path, leads)
    payload = json.loads(path.read_text())
    assert "ramp" in payload["companies"]          # keyed by normalized name
    assert payload["companies"]["ramp"]["employees"] == "900"


# ------------------------------------------------------------- tracks ---
def test_build_track_startups_paths(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "startups:\n  location: Austin, TX\n  locations: [austin]\n"
        "  output_file: data/companies.startups.yaml\n"
        "  reports_dir: reports/startups\n")
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    main = build_track(tmp_path, settings, "main")
    su = build_track(tmp_path, settings, "startups")
    assert main.is_startup is False
    assert su.is_startup is True
    assert su.location == "Austin, TX"
    assert su.locations == ["austin"]
    assert su.reports_dir == tmp_path / "reports" / "startups"
    assert su.corpus_dir != main.corpus_dir         # separate corpora
    assert su.registry_file == tmp_path / "data" / "companies.startups.yaml"


def test_discover_startups_end_to_end_offline(tmp_path, monkeypatch):
    """discover-startups with a stubbed source: a lead carrying an ATS URL
    resolves offline (URL classification, no probe), and both the registry and
    the metadata sidecar are written."""
    import jobsearch.sources as sources_mod
    from jobsearch.company_discovery import discover_companies

    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "search:\n  role_targeting: manual\n  query: senior software engineer\n"
        "  locations: [new york]\n"
        "startups:\n  sources: [stub]\n  location: New York, NY\n"
        "  locations: [new york]\n  output_file: data/companies.startups.yaml\n"
        "  meta_file: data/startup_meta.json\n")
    (tmp_path / "config" / "companies.yaml").write_text("companies: []\nmanual_check: []\n")
    (tmp_path / "data" / "resume.txt").write_text(
        "Senior Software Engineer. Python, distributed systems, APIs, backend.")

    def stub(session, ctx):
        return [CompanyLead(
            name="Ramp", sources=["ycombinator"], titles=["Corporate cards"],
            urls=["https://jobs.ashbyhq.com/ramp"],
            snippets=["Fintech startup, Series D, $300M, backed by Founders Fund."],
            meta={"name": "Ramp", "employees": "900", "stage": "Series D",
                  "investors": ["Y Combinator"], "source": "ycombinator"})]
    monkeypatch.setitem(sources_mod.SOURCES, "stub", stub)

    assert discover_companies(tmp_path, track_name="startups") == 0
    registry = (tmp_path / "data" / "companies.startups.yaml").read_text()
    assert "name: Ramp" in registry and "ats: ashby" in registry
    meta = json.loads((tmp_path / "data" / "startup_meta.json").read_text())
    ramp = meta["companies"]["ramp"]
    assert ramp["employees"] == "900"
    assert ramp["last_round_amount"] == "$300M"
    assert "Founders Fund" in ramp["investors"]


def test_load_registry_startups_isolated_from_main(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text("startups: {}\n")
    (tmp_path / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Google\n    ats: greenhouse\n    board: google\n")
    (tmp_path / "data" / "companies.startups.yaml").write_text(
        "companies:\n  - name: Ramp\n    ats: ashby\n    org: ramp\n"
        "    tags: [discovered]\nmanual_check: []\n")
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    main_companies, _ = load_registry(tmp_path, settings,
                                      build_track(tmp_path, settings, "main"))
    su_companies, _ = load_registry(tmp_path, settings,
                                    build_track(tmp_path, settings, "startups"))
    assert [c.name for c in main_companies] == ["Google"]   # FAANG only in main
    assert [c.name for c in su_companies] == ["Ramp"]       # startups only in startups
