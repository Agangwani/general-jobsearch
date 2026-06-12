"""Generic browser-harvest fallback: duck-typed records, JSON-LD JobPosting,
and DOM-embedded JSON parsing — all offline."""

from jobsearch.browser import parse_embedded
from jobsearch.fetchers import _generic


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
