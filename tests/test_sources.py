"""Company-lead sources: pure payload parsing, all offline."""

from jobsearch.sources.adzuna import parse_jobs as parse_adzuna
from jobsearch.sources.hn_hiring import parse_comment, parse_thread, pick_hiring_thread
from jobsearch.sources.themuse import parse_jobs as parse_muse

NYC = ["new york", "nyc", "brooklyn", "manhattan"]


# ------------------------------------------------------------------ The Muse ---

MUSE_PAYLOAD = {
    "page": 1,
    "page_count": 3,
    "results": [
        {
            "name": "Senior Software Engineer, Payments",
            "company": {"name": "Datadog"},
            "locations": [{"name": "New York, NY"}],
            "contents": "<p>Build <b>distributed</b> systems for payments.</p>",
        },
        {
            "name": "Staff Engineer",
            "company": {"name": "Remote-Only Co"},
            "locations": [{"name": "Flexible / Remote"}],
            "contents": "<p>Anywhere.</p>",
        },
        {  # no company name — dropped
            "name": "Mystery Role",
            "company": {},
            "locations": [{"name": "New York, NY"}],
        },
    ],
}


def test_muse_parse_filters_location_and_strips_html():
    leads = parse_muse(MUSE_PAYLOAD, NYC)
    assert [lead.name for lead in leads] == ["Datadog"]
    lead = leads[0]
    assert lead.sources == ["themuse"]
    assert lead.titles == ["Senior Software Engineer, Payments"]
    assert lead.locations == ["New York, NY"]
    assert "distributed" in lead.snippets[0]
    assert "<" not in lead.snippets[0]


def test_muse_parse_no_location_filter_keeps_everything_with_a_company():
    assert len(parse_muse(MUSE_PAYLOAD, [])) == 2


# -------------------------------------------------------------------- Adzuna ---

ADZUNA_PAYLOAD = {
    "results": [
        {
            "title": "Senior Backend Engineer",
            "company": {"display_name": "Peloton"},
            "location": {"display_name": "Manhattan, New York City"},
            "description": "Python, Kubernetes, and a bike.",
            "redirect_url": "https://www.adzuna.com/land/ad/123",
        },
        {
            "title": "Senior Engineer",
            "company": {"display_name": "Elsewhere Corp"},
            "location": {"display_name": "Austin, TX"},
            "description": "Not NYC.",
        },
    ]
}


def test_adzuna_parse_filters_location_and_skips_tracker_urls():
    leads = parse_adzuna(ADZUNA_PAYLOAD, NYC)
    assert [lead.name for lead in leads] == ["Peloton"]
    assert leads[0].titles == ["Senior Backend Engineer"]
    assert leads[0].urls == []  # redirect_url is Adzuna's tracker, not evidence


# ------------------------------------------------------- HN "Who is hiring?" ---

PIPE_COMMENT = (
    "Ramp (YC W19) | Senior Software Engineer, Backend | NYC (hybrid) | "
    '<a href="https:&#x2F;&#x2F;jobs.ashbyhq.com&#x2F;ramp" rel="nofollow">'
    "https:&#x2F;&#x2F;jobs.ashbyhq.com&#x2F;ramp</a>"
    "<p>We build finance automation. Python&#x2F;Go, Postgres, Kafka.</p>"
)


def test_parse_comment_pipe_header():
    lead = parse_comment(PIPE_COMMENT, NYC)
    assert lead.name == "Ramp"  # "(YC W19)" stripped
    assert lead.sources == ["hn_hiring"]
    assert "Senior Software Engineer, Backend" in lead.titles[0]
    assert lead.urls == ["https://jobs.ashbyhq.com/ramp"]  # entities unescaped
    assert "finance automation" in lead.snippets[0]


def test_parse_comment_is_hiring_sentence():
    text = ("Hebbia is hiring senior full-stack engineers in New York."
            "<p>We do AI for finance.</p>")
    lead = parse_comment(text, NYC)
    assert lead.name == "Hebbia"
    assert "senior full-stack engineers" in lead.titles[0]


def test_parse_comment_rejects_wrong_location_and_junk_headers():
    assert parse_comment("Acme | Senior Engineer | Berlin, Germany", NYC) is None
    # URL as the company segment is not a company name
    assert parse_comment("https://acme.com/jobs | Engineer | NYC", NYC) is None
    # prose headers without the hiring convention are skipped
    assert parse_comment("We are a small team doing big things in NYC", NYC) is None
    assert parse_comment("", NYC) is None


def test_parse_thread_walks_top_level_comments_only():
    item = {
        "children": [
            {"text": PIPE_COMMENT,
             "children": [{"text": "Reply Co | Engineer | NYC"}]},
            {"text": None},
            {"text": "Brooklyn Robotics | Staff Software Engineer | Brooklyn, NY"},
        ]
    }
    leads = parse_thread(item, NYC)
    assert [lead.name for lead in leads] == ["Ramp", "Brooklyn Robotics"]


def test_pick_hiring_thread_skips_sibling_bot_threads():
    payload = {
        "hits": [
            {"objectID": "111", "title": "Ask HN: Who wants to be hired? (June 2026)"},
            {"objectID": "222", "title": "Ask HN: Who is hiring? (June 2026)"},
        ]
    }
    assert pick_hiring_thread(payload) == 222
    assert pick_hiring_thread({"hits": []}) is None


# --------------------------------------------------------------- ATS boards ---
from jobsearch.sources.ats_boards import (  # noqa: E402
    fetch as ats_fetch, parse_ashby, parse_greenhouse, parse_lever,
)


def test_ats_greenhouse_parse_filters_location_and_builds_evidence():
    payload = {"jobs": [
        {"title": "Senior Backend Engineer", "absolute_url": "https://gh/acme/1",
         "location": {"name": "New York, NY"},
         "content": "<p>Build <b>distributed</b> systems.</p>"},
        {"title": "Barista", "absolute_url": "https://gh/acme/2",
         "location": {"name": "Austin, TX"}, "content": "Coffee."},
    ]}
    leads = parse_greenhouse(payload, "Acme", "acme", NYC)
    assert [l.name for l in leads] == ["Acme"]               # Austin filtered out
    lead = leads[0]
    assert lead.sources == ["ats_boards"]
    assert lead.titles == ["Senior Backend Engineer"]
    assert lead.snippets == ["Build distributed systems."]   # HTML stripped
    assert "https://job-boards.greenhouse.io/acme" in lead.urls   # board url → free resolve


def test_ats_lever_parse_list_payload():
    payload = [
        {"text": "Staff Engineer", "hostedUrl": "https://jobs.lever.co/ramp/1",
         "categories": {"location": "New York"}, "descriptionPlain": "Payments infra."},
        {"text": "Remote SRE", "categories": {"location": "Remote - US"},
         "descriptionPlain": "On-call."},
    ]
    leads = parse_lever(payload, "Ramp", "ramp", NYC)
    assert [l.titles[0] for l in leads] == ["Staff Engineer"]   # only NYC kept
    assert "https://jobs.lever.co/ramp" in leads[0].urls


def test_ats_ashby_prefers_payload_org_name():
    payload = {"name": "Linear", "jobs": [
        {"title": "Product Engineer", "location": "New York, NY",
         "jobUrl": "https://jobs.ashbyhq.com/linear/1",
         "descriptionPlain": "Ship product."}]}
    leads = parse_ashby(payload, "seed-name", "linear", NYC)
    assert leads[0].name == "Linear"                          # payload name wins over seed


def test_ats_no_location_filter_keeps_all():
    payload = {"jobs": [{"title": "Anything", "location": {"name": "Nowhere"},
                         "content": "x", "absolute_url": ""}]}
    assert len(parse_greenhouse(payload, "Acme", "acme", [])) == 1


def test_ats_fetch_skips_dead_boards_and_unknown_ats(monkeypatch):
    import jobsearch.sources.ats_boards as mod
    def fake_get_json(session, url):
        if "ramp" in url:
            raise RuntimeError("502")                          # dead board
        return {"jobs": [{"title": "Eng", "location": {"name": "New York"},
                          "content": "x", "absolute_url": ""}]}
    monkeypatch.setattr(mod, "get_json", fake_get_json)
    ctx = {"location_subs": NYC, "ats_boards": [
        {"ats": "greenhouse", "token": "acme", "name": "Acme"},
        {"ats": "lever", "token": "ramp"},                    # errors → skipped
        {"ats": "workday", "token": "x"},                     # unknown ats → skipped
        {"ats": "greenhouse"},                                # no token → skipped
    ]}
    leads = ats_fetch(None, ctx)
    assert [l.name for l in leads] == ["Acme"]                # only the healthy board
