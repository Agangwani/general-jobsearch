"""The pipeline must degrade cleanly when Playwright/Chromium is unavailable."""

import jobsearch.pipeline as pipeline
from jobsearch.browser import BrowserUnavailable
from jobsearch.models import Company


def test_browser_companies_get_actionable_error(monkeypatch):
    def boom(*args, **kwargs):
        raise BrowserUnavailable("playwright not installed — pip install playwright")

    monkeypatch.setattr(pipeline, "BrowserRuntime", boom)
    companies = [Company(name="Goldman Sachs", ats="browser_goldman")]
    jobs, errors = pipeline.fetch_all(companies, {"fetch": {"max_workers": 2}})
    assert jobs == []
    assert len(errors) == 1
    assert errors[0].company == "Goldman Sachs"
    assert "playwright" in errors[0].error


def test_api_failure_routes_to_browser_fallback(monkeypatch):
    """A company with fallback: browser_meta should hit the browser pass when
    its API fetcher raises, and surface both errors if that also fails."""

    def api_boom(company, session, settings):
        raise RuntimeError("doc_id rotated")

    def browser_boom(company, runtime, settings):
        raise RuntimeError("graphql capture empty")

    class FakeRuntime:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setitem(pipeline.FETCHERS, "meta", api_boom)
    monkeypatch.setitem(pipeline.BROWSER_FETCHERS, "browser_meta", browser_boom)
    monkeypatch.setattr(pipeline, "BrowserRuntime", FakeRuntime)

    companies = [Company(name="Meta", ats="meta", params={"fallback": "browser_meta"})]
    jobs, errors = pipeline.fetch_all(companies, {"fetch": {"max_workers": 2}})
    assert jobs == []
    assert len(errors) == 1
    assert "doc_id rotated" in errors[0].error and "graphql capture empty" in errors[0].error


def test_unknown_ats_is_reported():
    companies = [Company(name="Mystery", ats="carrier-pigeon")]
    jobs, errors = pipeline.fetch_all(companies, {"fetch": {"max_workers": 2}})
    assert errors and "unknown ats type" in errors[0].error
