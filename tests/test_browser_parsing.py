"""Offline tests for browser-fetcher parsing (captured-XHR fixtures, no browser)."""

from jobsearch.fetchers import deshaw, eightfold, goldman, janestreet, jpmorgan, microsoft, millennium, tiktok
from jobsearch.models import Company, JobPosting
from jobsearch.utils import first, walk_collect


class _MatchAll:
    """Stand-in JobFilter that passes every job, so description-enrichment tests
    exercise the enrichment logic without depending on filter config."""

    def __init__(self, _search):
        pass

    def matches(self, _job):
        return True


def test_walk_collect_finds_nested_records():
    payload = {"data": {"results": {"hits": [{"title": "SWE", "jobId": "1"}, {"noise": True}]}}}
    found = walk_collect(payload, lambda d: "title" in d and "jobId" in d)
    assert found == [{"title": "SWE", "jobId": "1"}]


def test_first_falls_through_empty_values():
    assert first({"a": "", "b": None, "c": "x"}, ("a", "b", "c")) == "x"
    assert first({}, ("a",), default=None) is None


def test_goldman_parse():
    payloads = [{"results": {"items": [{
        "jobTitle": "Vice President, Software Engineering",
        "jobId": "12345",
        "location": "New York",
        "postedDate": "2026-06-08",
        "division": "Engineering",
    }]}}]
    jobs = goldman.parse_payloads(payloads, "Goldman Sachs")
    assert len(jobs) == 1
    assert jobs[0].url == "https://higher.gs.com/roles/12345"
    assert jobs[0].posted_at.day == 8
    assert jobs[0].source == "goldman"


def test_jpmorgan_parse_oracle_shape():
    payloads = [{"items": [{"requisitionList": [{
        "Title": "Senior Software Engineer III",
        "Id": "210512345",
        "PrimaryLocation": "New York, NY, United States",
        "PostedDate": "2026-06-09",
    }]}]}]
    jobs = jpmorgan.parse_payloads(payloads, "JPMorgan Chase")
    assert len(jobs) == 1
    assert jobs[0].url == ("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience"
                           "/en/sites/CX_1001/job/210512345")
    assert jobs[0].posted_at is not None


def test_millennium_parse_phenom_shape():
    payloads = [{"data": {"jobs": [{
        "title": "Senior Software Engineer",
        "jobSeqNo": "MLPUS123",
        "cityStateCountry": "New York, NY, US",
        "postedDate": "2026-06-10T00:00:00Z",
        "descriptionTeaser": "Build trading infrastructure",
        "applyUrl": "https://www.mlp.com/job/MLPUS123",
    }]}}]
    jobs = millennium.parse_payloads(payloads, "Millennium")
    assert jobs[0].url == "https://www.mlp.com/job/MLPUS123"
    assert jobs[0].description == "Build trading infrastructure"


def test_tiktok_parse():
    payloads = [{"data": {"job_post_list": [{
        "id": "7400001",
        "title": "Senior Software Engineer, Backend",
        "city_info": {"name": "New York"},
        "publish_time": 1765400000000,
        "description": "<p>Build recommendation infra</p>",
    }]}}]
    jobs = tiktok.parse_payloads(payloads, "TikTok")
    assert jobs[0].location == "New York"
    assert jobs[0].url == "https://lifeattiktok.com/search/7400001"
    assert "recommendation infra" in jobs[0].description
    assert jobs[0].posted_at is not None


def test_janestreet_json_and_dom_fallback():
    payloads = [[{"position": "Software Engineer", "id": "sw-eng-ny", "city": "NYC"}]]
    jobs = janestreet.parse_payloads(payloads, "Jane Street")
    assert jobs[0].url.endswith("/position/sw-eng-ny/")

    links = [
        {"text": "Software Engineer\nNew York", "href": "https://www.janestreet.com/join-jane-street/position/sw-eng-ny/"},
        {"text": "", "href": "https://www.janestreet.com/join-jane-street/position/empty/"},
        {"text": "About us", "href": "https://www.janestreet.com/about/"},
    ]
    dom_jobs = janestreet.parse_links(links, "Jane Street")
    assert len(dom_jobs) == 1
    assert dom_jobs[0].title == "Software Engineer"


def test_microsoft_enrich_populates_description(monkeypatch):
    """The search endpoint returns title-only stubs; enrichment must pull the
    body from the per-job detail endpoint and strip HTML (regression guard for
    the empty-description skew — whole companies were scored on title alone)."""
    monkeypatch.setattr(microsoft, "JobFilter", _MatchAll)
    monkeypatch.setattr(microsoft, "get_json", lambda session, url, params=None: {
        "operationResult": {"result": {
            "description": "<p>Build distributed backend systems.</p>",
            "responsibilities": "Own reliability.", "qualifications": "5+ years."}}})
    job = JobPosting(company="Microsoft", title="Senior Software Engineer",
                     location="New York", url="", job_id="42", description="", source="microsoft")
    microsoft.enrich_descriptions([job], object(), {})
    assert "distributed backend systems" in job.description
    assert "reliability" in job.description
    assert "<" not in job.description  # HTML stripped


def test_microsoft_enrich_is_graceful_on_error(monkeypatch):
    """A failed detail fetch must not abort the run; the title-only posting
    survives (it still scores on its title)."""
    def boom(*a, **k):
        raise RuntimeError("502 from detail API")
    monkeypatch.setattr(microsoft, "JobFilter", _MatchAll)
    monkeypatch.setattr(microsoft, "get_json", boom)
    job = JobPosting(company="Microsoft", title="Senior Software Engineer",
                     location="New York", url="", job_id="1", description="", source="microsoft")
    microsoft.enrich_descriptions([job], object(), {})  # must not raise
    assert job.description == ""


def test_eightfold_enrich_populates_description(monkeypatch):
    monkeypatch.setattr(eightfold, "JobFilter", _MatchAll)
    monkeypatch.setattr(eightfold, "get_json", lambda session, url, params=None: {
        "position": {"job_description": "<ul><li>Kafka, Python, distributed systems</li></ul>"}})
    job = JobPosting(company="Netflix", title="Senior Software Engineer",
                     location="New York", url="", job_id="9", description="", source="eightfold")
    eightfold.enrich_descriptions([job], object(), "https://netflix.eightfold.ai", "netflix", {})
    assert "Kafka" in job.description and "<" not in job.description


def test_eightfold_enrich_skips_jobs_that_already_have_a_description(monkeypatch):
    """Enrichment must not overwrite a description the list endpoint already
    provided, and must not fire a needless detail request."""
    calls = []
    monkeypatch.setattr(eightfold, "JobFilter", _MatchAll)
    monkeypatch.setattr(eightfold, "get_json",
                        lambda *a, **k: calls.append(1) or {"position": {}})
    job = JobPosting(company="Netflix", title="SWE", location="NY", url="", job_id="9",
                     description="Already have the full body.", source="eightfold")
    eightfold.enrich_descriptions([job], object(), "https://x.eightfold.ai", "netflix", {})
    assert job.description == "Already have the full body."
    assert calls == []


def test_janestreet_strips_html_from_description():
    # Jane Street's JSON overview is raw HTML with inline styles; if it isn't
    # stripped, tag/style tokens (li, h3, span style, font weight) leak into the
    # TF-IDF space and form a spurious markup cluster that skews the fit map.
    payloads = [[{
        "position": "Front End Software Engineer",
        "id": "fe-swe",
        "city": "New York",
        "overview": '<h3>The Role</h3><ul><li style="font-weight:400">Build UIs</li>'
                    '<li>Ship <span style="font-weight:700">React</span></li></ul>',
    }]]
    jobs = janestreet.parse_payloads(payloads, "Jane Street")
    desc = jobs[0].description
    assert "<" not in desc and ">" not in desc
    for markup in ("li", "h3", "span", "style", "font-weight"):
        assert markup not in desc.lower().split()
    assert "Build UIs" in desc and "React" in desc


def test_deshaw_link_parse():
    links = [
        {"text": "Senior Software Developer\nNew York", "href": "https://www.deshaw.com/careers/senior-software-developer-5135?ref=x"},
        {"text": "Choose your path", "href": "https://www.deshaw.com/careers/choose-your-path"},
        {"text": "Senior Software Developer\nNew York", "href": "https://www.deshaw.com/careers/senior-software-developer-5135"},
    ]
    jobs = deshaw.parse_links(links, "D. E. Shaw")
    assert len(jobs) == 1  # dedup + non-role links dropped
    assert jobs[0].job_id == "senior-software-developer-5135"


class FakeRuntime:
    def __init__(self, matched=None, extra=None, embedded=None):
        self._harvest = {"matched": matched or [], "extra": extra or [],
                         "embedded": embedded or []}

    def harvest(self, url, pattern, settle_ms=8000, attempts=2):
        return self._harvest

    def capture_json(self, url, pattern, settle_ms=8000):
        return self._harvest["matched"]

    def extract_links(self, url, selector, wait_selector=None):
        return []


def test_browser_fetchers_raise_when_empty():
    import pytest

    company = Company(name="Goldman Sachs", ats="browser_goldman")
    with pytest.raises(RuntimeError):
        goldman.fetch(company, FakeRuntime(), {})


def test_phenom_embedded_state_feeds_jpmorgan():
    # careers.jpmorgan.com (Phenom) embeds page-1 results in window.phApp.ddo
    # — no XHR needs to fire for the fetch to succeed.
    ddo = {"eagerLoadRefineSearch": {"data": {"jobs": [{
        "title": "Senior Software Engineer III",
        "jobSeqNo": "210512345",
        "cityStateCountry": "New York, NY, US",
        "postedDate": "2026-06-09",
        "descriptionTeaser": "Build payments infrastructure",
        "applyUrl": "https://careers.jpmorgan.com/us/en/job/210512345",
    }]}}}
    company = Company(name="JPMorgan Chase", ats="browser_jpmorgan")
    jobs = jpmorgan.fetch(company, FakeRuntime(embedded=[ddo]), {})
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Software Engineer III"
    assert jobs[0].url.endswith("/210512345")


def test_generic_fallback_rescues_unknown_shape():
    # A response shape none of the site key maps know (e.g. the board
    # changed vendors) — the generic pass still extracts it.
    weird = {"payload": {"openings": [{
        "positionTitle": "Senior Software Engineer",
        "jobPostingId": "GS-99",
        "primaryLocation": "New York",
        "datePosted": "2026-06-10",
    }]}}
    company = Company(name="Goldman Sachs", ats="browser_goldman")
    jobs = goldman.fetch(company, FakeRuntime(extra=[weird]), {})
    assert len(jobs) == 1
    assert jobs[0].url == "https://higher.gs.com/roles/GS-99"
    assert jobs[0].source == "goldman"


def test_deshaw_clean_title():
    from jobsearch.fetchers.deshaw import clean_title

    title, blurb = clean_title(
        "iconStart-up Ventures: Senior Software Engineer at Wisable: Wisable, a "
        "tech-enabled business brokerage that spun out from D. E. Shaw's venture "
        "studio, seeks a senior software engineer..."
    )
    assert title == "Senior Software Engineer at Wisable"
    assert "brokerage" in blurb

    title, _ = clean_title("iconSystems: Senior Linux Infrastructure Engineer (London): The D. E. Shaw group seeks...")
    assert title == "Senior Linux Infrastructure Engineer (London)"

    title, blurb = clean_title("Plain Title")
    assert title == "Plain Title" and blurb == ""
