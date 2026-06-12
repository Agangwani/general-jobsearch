"""Generic browser-harvest fallback: duck-typed records, JSON-LD JobPosting,
and DOM-embedded JSON parsing — all offline."""

from jobsearch.browser import parse_embedded, parse_json_text
from jobsearch.fetchers import _generic


def test_parse_json_text_strips_xssi_guards():
    # Google prefixes JSON bodies with )]}' which breaks Response.json()
    assert parse_json_text(")]}'\n{\"jobs\": [1]}") == {"jobs": [1]}
    assert parse_json_text("while(1);[{\"a\": 1}]") == [{"a": 1}]
    assert parse_json_text('{"plain": true}') == {"plain": True}
    assert parse_json_text("<html>nope</html>") is None
    assert parse_json_text('"just a string"') is None
    assert parse_json_text("") is None


def test_debug_summary_describes_harvest():
    harvest = {"matched": [1], "extra": [2, 3], "embedded": [],
               "debug": {"final_url": "https://x.com/careers",
                         "response_urls": ["https://x.com/api/a", "https://x.com/api/b"]}}
    s = _generic.debug_summary(harvest)
    assert "final URL: https://x.com/careers" in s
    assert "1 matched + 2 other JSON responses" in s
    assert "https://x.com/api/a" in s


def test_goldman_pattern_matches_api_subdomain():
    # Run diagnostics showed the real endpoint on the api- subdomain.
    import re
    from jobsearch.fetchers.goldman import XHR_PATTERN
    assert re.search(XHR_PATTERN, "https://api-higher.gs.com/gateway/api/v1/graphql")
    assert re.search(XHR_PATTERN, "https://higher.gs.com/api/roles")
    assert not re.search(XHR_PATTERN, "https://higher.gs.com/results?page=1")


def test_jpmorgan_targets_oracle_site():
    from jobsearch.fetchers.jpmorgan import URL, XHR_PATTERN
    import re
    assert "jpmc.fa.oraclecloud.com" in URL
    assert re.search(XHR_PATTERN, "https://jpmc.fa.oraclecloud.com/hcmRestApi/scrs/"
                                  "sites/CX_1001/recruitingCEJobRequisitions?onlyData=true")


def test_google_card_title_from_slug():
    from jobsearch.fetchers.google import parse_cards
    links = [
        {"text": "Apply", "href": "/about/careers/applications/jobs/results/"
                                  "987654-senior-software-engineer-infrastructure"},
        {"text": "", "href": "https://fonts.googleapis.com/css2"},
    ]
    jobs = parse_cards(links, "Google")
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Software Engineer Infrastructure"


def test_google_card_scrape():
    from jobsearch.fetchers.google import parse_cards
    links = [
        {"text": "Learn more about Senior Software Engineer, Core",
         "href": "https://www.google.com/about/careers/applications/jobs/results/123456-senior"},
        {"text": "Senior Staff Software Engineer\nNew York, NY", "href": "/jobs/results/789"},
        {"text": "Learn more about Senior Software Engineer, Core",
         "href": "https://www.google.com/about/careers/applications/jobs/results/123456-senior"},  # dup
        {"text": "About Google", "href": "https://about.google/"},
    ]
    jobs = parse_cards(links, "Google")
    assert [j.title for j in jobs] == [
        "Senior Software Engineer, Core", "Senior Staff Software Engineer"]
    assert jobs[0].job_id == "123456"
    assert jobs[0].url.endswith("/jobs/results/123456")


def test_parse_embedded_drops_non_json():
    blobs = ['{"a": 1}', "not json", '[]', '[{"title": "x"}]', None]
    parsed = parse_embedded(blobs)
    assert parsed == [{"a": 1}, [{"title": "x"}]]  # empty list dropped too


def test_looks_like_job():
    assert _generic.looks_like_job({
        "title": "Senior Software Engineer", "jobId": "1", "location": "NYC"})
    assert _generic.looks_like_job({
        "name": "Backend Engineer", "id": 7, "url": "https://x.com/jobs/7"})
    # no id evidence
    assert not _generic.looks_like_job({"title": "Senior SWE", "location": "NYC"})
    # no location/url evidence (config objects often have name+id)
    assert not _generic.looks_like_job({"name": "darkMode", "id": "flag-1"})
    # title not a plausible role string
    assert not _generic.looks_like_job({"title": "OK", "id": 1, "location": "x"})
    assert not _generic.looks_like_job({"title": ["a", "b"], "id": 1, "location": "x"})


def test_jsonld_jobposting_extracted_first():
    harvest = {"matched": [], "extra": [], "embedded": [[{
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Software Engineer",
        "datePosted": "2026-06-10",
        "description": "<p>Build infra</p>",
        "url": "https://example.com/jobs/42",
        "jobLocation": {"@type": "Place",
                        "address": {"addressLocality": "New York",
                                    "addressRegion": "NY"}},
    }]]}
    jobs = _generic.fallback_jobs(harvest, "Example", "example")
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Software Engineer"
    assert jobs[0].location == "New York, NY"
    assert jobs[0].url == "https://example.com/jobs/42"
    assert jobs[0].description == "Build infra"
    assert jobs[0].posted_at.day == 10


def test_fallback_dedupes_across_sources():
    record = {"title": "Senior Software Engineer", "jobId": "9",
              "location": "New York", "applyUrl": "https://x.com/9"}
    harvest = {"matched": [{"jobs": [record]}], "extra": [[record]],
               "embedded": []}
    jobs = _generic.fallback_jobs(harvest, "X", "x")
    assert len(jobs) == 1


def test_location_shapes_normalized():
    harvest = {"matched": [[
        {"title": "Senior Software Engineer", "jobId": "1",
         "locations": ["New York, NY", "Remote - US"]},
        {"title": "Senior Backend Engineer", "jobId": "2",
         "location": {"name": "Brooklyn"}},
    ]], "extra": [], "embedded": []}
    jobs = _generic.fallback_jobs(harvest, "X", "x", link_fmt="https://x.com/{id}")
    assert jobs[0].location == "New York, NY, Remote - US"
    assert jobs[1].location == "Brooklyn"
    assert jobs[1].url == "https://x.com/2"
