"""ATS platform detection, URL canonicalization, and Greenhouse schema
parsing. Pure logic — no network, no browser."""

from webapp import ats


# ------------------------------------------------------------- detection
def test_detect_platform():
    assert ats.detect_platform(
        "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=7701651"
    ) == ats.GREENHOUSE
    # Company-branded board: only the gh_jid betrays Greenhouse underneath.
    assert ats.detect_platform(
        "https://www.coinbase.com/careers/positions/7701651?gh_jid=7701651"
    ) == ats.GREENHOUSE
    assert ats.detect_platform("https://jobs.ashbyhq.com/openai/abc") == ats.ASHBY
    assert ats.detect_platform("https://app.careerpuck.com/x/y") == ats.ASHBY
    assert ats.detect_platform("https://jobs.lever.co/brex/uuid") == ats.LEVER
    assert ats.detect_platform(
        "https://etsy.wd5.myworkdayjobs.com/Etsy_Careers/job/x") == ats.WORKDAY
    assert ats.detect_platform("https://www.janestreet.com/join/role") == ats.CUSTOM
    assert ats.detect_platform("") == ats.CUSTOM


# ------------------------------------------------------- greenhouse parsing
def test_parse_greenhouse_both_dialects_and_hosted():
    # new embed dialect: for=board, token=id
    assert ats.parse_greenhouse(
        "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=7701651"
    ) == ("coinbase", "7701651", "job-boards.greenhouse.io")
    # legacy embed dialect: token=board, gh_jid=id
    assert ats.parse_greenhouse(
        "https://boards.greenhouse.io/embed/job_app?token=stripe&gh_jid=42"
    ) == ("stripe", "42", "boards.greenhouse.io")
    # hosted posting path
    assert ats.parse_greenhouse(
        "https://job-boards.greenhouse.io/datadog/jobs/12345"
    ) == ("datadog", "12345", "job-boards.greenhouse.io")
    # branded URL without a board → unknown (handled at runtime via iframe hoist)
    assert ats.parse_greenhouse(
        "https://www.coinbase.com/careers/positions/7701651?gh_jid=7701651") is None


def test_canonical_apply_url():
    # hosted greenhouse → bare embed form, same host family
    assert ats.canonical_apply_url(
        "https://job-boards.greenhouse.io/coinbase/jobs/7701651"
    ) == "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=7701651"
    assert ats.canonical_apply_url(
        "https://boards.greenhouse.io/stripe/jobs/42"
    ) == "https://boards.greenhouse.io/embed/job_app?token=stripe&gh_jid=42"
    # ashby gets /application; lever gets /apply
    assert ats.canonical_apply_url(
        "https://jobs.ashbyhq.com/openai/abc-123"
    ) == "https://jobs.ashbyhq.com/openai/abc-123/application"
    assert ats.canonical_apply_url(
        "https://jobs.lever.co/brex/uuid"
    ) == "https://jobs.lever.co/brex/uuid/apply"
    # idempotent: already on the form page
    assert ats.canonical_apply_url(
        "https://jobs.ashbyhq.com/openai/abc-123/application"
    ) == "https://jobs.ashbyhq.com/openai/abc-123/application"
    # branded + custom pass through untouched
    branded = "https://www.coinbase.com/careers/positions/7701651?gh_jid=7701651"
    assert ats.canonical_apply_url(branded) == branded


# ----------------------------------------------------- schema flattening
SAMPLE_PAYLOAD = {
    "title": "Senior Software Engineer",
    "questions": [
        {"label": "First Name", "required": True,
         "fields": [{"name": "first_name", "type": "input_text", "values": []}]},
        {"label": "Resume/CV", "required": True, "fields": [
            {"name": "resume", "type": "input_file", "values": []},
            {"name": "resume_text", "type": "textarea", "values": []},
        ]},
        {"label": "Are you legally authorized to work in the US?", "required": True,
         "fields": [{"name": "question_555", "type": "multi_value_single_select",
                     "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
    ],
}


def test_parse_greenhouse_payload():
    schema = ats.parse_greenhouse_payload(SAMPLE_PAYLOAD)
    assert schema["first_name"] == {
        "label": "First Name", "required": True, "type": "input_text", "options": []}
    # the file + text pair both land under the same Resume label
    assert schema["resume"]["type"] == "input_file"
    assert schema["resume_text"]["type"] == "textarea"
    sel = schema["question_555"]
    assert sel["type"] == "multi_value_single_select"
    assert sel["options"] == [{"value": "1", "text": "Yes"}, {"value": "0", "text": "No"}]


def test_greenhouse_field_name_and_select_type():
    assert ats.greenhouse_field_name("job_application[first_name]") == "first_name"
    assert ats.greenhouse_field_name("job_application[question_555]") == "question_555"
    assert ats.greenhouse_field_name("random[x]") == ""
    assert ats.is_greenhouse_select_type("multi_value_single_select")
    assert not ats.is_greenhouse_select_type("input_text")


def test_greenhouse_job_id_across_url_forms():
    # the open embed form and the stored branded posting share the gh job id —
    # this is how 'fill all open tabs' attributes a tab back to a tracked job.
    assert ats.greenhouse_job_id(
        "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=7701651") == "7701651"
    assert ats.greenhouse_job_id(
        "https://www.coinbase.com/careers/positions/7701651?gh_jid=7701651") == "7701651"
    assert ats.greenhouse_job_id("https://job-boards.greenhouse.io/datadog/jobs/12345") == "12345"
    assert ats.greenhouse_job_id("https://jobs.ashbyhq.com/openai/uuid") == ""
