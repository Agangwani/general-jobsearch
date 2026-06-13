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
