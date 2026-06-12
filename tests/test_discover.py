"""ATS slug auto-discovery: pure URL classification, slug candidates, and
stanza emission — all offline."""

from jobsearch.discover import (
    classify_ats_url, emit_stanza, hop_candidates, slug_candidates, survey_urls,
)


def test_hop_candidates_prefers_same_site_job_links():
    hrefs = [
        "https://superhuman.com/company/careers",          # current page — skipped
        "https://superhuman.com/company/careers#values",   # fragment of current — skipped
        "https://superhuman.com/company/careers/open-roles",
        "https://superhuman.com/blog/post",                # not job-ish
        "https://twitter.com/superhuman",                  # not job-ish
        "mailto:jobs@superhuman.com",                      # not http
    ]
    hops = hop_candidates(hrefs, "https://superhuman.com/company/careers")
    assert hops == ["https://superhuman.com/company/careers/open-roles"]
    # hosted-board links in the DOM are direct detections, not hops
    assert survey_urls(["https://job-boards.greenhouse.io/superhuman"]) == [
        {"ats": "greenhouse", "board": "superhuman"}]


def test_hop_candidates_dedupes():
    hrefs = ["https://x.com/jobs", "https://x.com/jobs/", "https://www.x.com/jobs#a"]
    hops = hop_candidates(hrefs, "https://x.com/careers")
    assert hops == ["https://x.com/jobs"]


def test_greenhouse_urls():
    assert classify_ats_url(
        "https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true"
    ) == {"ats": "greenhouse", "board": "datadog"}
    assert classify_ats_url(
        "https://boards.greenhouse.io/embed/job_board?for=warbyparker&b=https%3A%2F%2F..."
    ) == {"ats": "greenhouse", "board": "warbyparker"}
    assert classify_ats_url(
        "https://job-boards.greenhouse.io/stripe") == {"ats": "greenhouse", "board": "stripe"}
    # the 'embed' path segment must not be mistaken for a slug
    assert classify_ats_url("https://boards.greenhouse.io/embed/job_app?token=1") is None


def test_lever_and_ashby_urls():
    assert classify_ats_url(
        "https://api.lever.co/v0/postings/plaid?mode=json") == {"ats": "lever", "org": "plaid"}
    assert classify_ats_url(
        "https://jobs.lever.co/superhuman") == {"ats": "lever", "org": "superhuman"}
    assert classify_ats_url(
        "https://api.ashbyhq.com/posting-api/job-board/ramp") == {"ats": "ashby", "org": "ramp"}
    assert classify_ats_url("https://jobs.ashbyhq.com/notion") == {"ats": "ashby", "org": "notion"}


def test_workday_urls():
    assert classify_ats_url(
        "https://citadel.wd5.myworkdayjobs.com/wday/cxs/citadel/External/jobs"
    ) == {"ats": "workday", "tenant": "citadel",
          "host": "citadel.wd5.myworkdayjobs.com", "site": "External"}
    assert classify_ats_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    ) == {"ats": "workday", "tenant": "nvidia",
          "host": "nvidia.wd5.myworkdayjobs.com", "site": "NVIDIAExternalCareerSite"}


def test_eightfold_and_smartrecruiters():
    assert classify_ats_url("https://morganstanley.eightfold.ai/api/apply/v2/jobs?q=x") == {
        "ats": "eightfold", "base_url": "https://morganstanley.eightfold.ai"}
    assert classify_ats_url("https://api.smartrecruiters.com/v1/companies/Visa/postings") == {
        "ats": "smartrecruiters", "org": "Visa"}


def test_irrelevant_urls_ignored():
    for url in ("https://cdn.example.com/app.js",
                "https://www.googletagmanager.com/gtm.js",
                "https://company.com/careers"):
        assert classify_ats_url(url) is None


def test_survey_dedupes_and_keeps_order():
    urls = [
        "https://cdn.x.com/a.js",
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        "https://boards-api.greenhouse.io/v1/boards/acme/departments",  # same board
        "https://jobs.lever.co/acme",
    ]
    detections = survey_urls(urls)
    assert detections == [{"ats": "greenhouse", "board": "acme"},
                          {"ats": "lever", "org": "acme"}]


def test_slug_candidates():
    assert slug_candidates("Warby Parker") == ["warbyparker", "warby-parker", "warby"]
    assert slug_candidates("Plaid") == ["plaid"]
    assert slug_candidates("D. E. Shaw") == ["deshaw", "d-e-shaw", "d"]


def test_emit_stanza_greenhouse():
    stanza = emit_stanza("Warby Parker", {"ats": "greenhouse", "board": "warbyparker"},
                         "https://www.warbyparker.com/careers")
    assert "- name: Warby Parker" in stanza
    assert "ats: greenhouse" in stanza
    assert "board: warbyparker" in stanza
    assert "careers_url: https://www.warbyparker.com/careers" in stanza


def test_emit_stanza_workday():
    stanza = emit_stanza("Citadel", {"ats": "workday", "tenant": "citadel",
                                     "host": "citadel.wd5.myworkdayjobs.com",
                                     "site": "External"})
    for line in ("ats: workday", "tenant: citadel",
                 "host: citadel.wd5.myworkdayjobs.com", "site: External"):
        assert line in stanza
