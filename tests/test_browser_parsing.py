"""Offline tests for browser-fetcher parsing (captured-XHR fixtures, no browser)."""

from jobsearch.fetchers import deshaw, goldman, janestreet, jpmorgan, millennium, tiktok
from jobsearch.models import Company
from jobsearch.utils import first, walk_collect


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
    assert jobs[0].url == "https://careers.jpmorgan.com/us/en/job/210512345"
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


def test_deshaw_link_parse():
    links = [
        {"text": "Senior Software Developer\nNew York", "href": "https://www.deshaw.com/careers/senior-software-developer-5135?ref=x"},
        {"text": "Choose your path", "href": "https://www.deshaw.com/careers/choose-your-path"},
        {"text": "Senior Software Developer\nNew York", "href": "https://www.deshaw.com/careers/senior-software-developer-5135"},
    ]
    jobs = deshaw.parse_links(links, "D. E. Shaw")
    assert len(jobs) == 1  # dedup + non-role links dropped
    assert jobs[0].job_id == "senior-software-developer-5135"


def test_browser_fetchers_raise_when_empty():
    import pytest

    class FakeRuntime:
        def capture_json(self, url, pattern, settle_ms=8000):
            return []

        def extract_links(self, url, selector, wait_selector=None):
            return []

    company = Company(name="Goldman Sachs", ats="browser_goldman")
    with pytest.raises(RuntimeError):
        goldman.fetch(company, FakeRuntime(), {})


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
