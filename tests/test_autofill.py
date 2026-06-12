"""Auto-fill engine tests: pure plan() logic over field descriptors, value
formatting, and the description formatter. No browser needed."""

from webapp.autofill import (
    format_phone, format_salary, format_url, parse_location, plan, split_name,
)
from webapp.textfmt import description_html

PROFILE = {
    "full_name": "Alex Candidate",
    "email": "alex@example.com",
    "phone": "212-555-0147",
    "location": "New York, NY",
    "linkedin": "linkedin.com/in/alex",
    "github": "github.com/alex",
    "portfolio": "",
    "current_title": "Senior Software Engineer",
    "current_company": "Capital One",
    "years_experience": "7",
    "work_authorization": "US Citizen",
    "requires_sponsorship": "No",
    "salary_expectation": "200000",
    "notice_period": "2 weeks",
    "preferred_pronouns": "",
}


def fld(af="f0-0", kind="text", **kw):
    base = {"af": af, "kind": kind, "name": "", "id": "", "label": "",
            "placeholder": "", "autocomplete": "", "question": "",
            "options": [], "value": "", "checked": False}
    base.update(kw)
    return base


def one(fields, **kw):
    return plan(fields if isinstance(fields, list) else [fields], PROFILE, **kw)


# ------------------------------------------------------------------ formatting
def test_value_formatting():
    assert split_name("Alex Candidate") == ("Alex", "Candidate")
    assert split_name("Cher") == ("Cher", "")
    assert parse_location("New York, NY") == ("New York", "New York")
    assert format_phone("212-555-0147") == "(212) 555-0147"
    assert format_phone("+1 212 555 0147") == "(212) 555-0147"
    assert format_salary("200000") == "$200,000"
    assert format_salary("$180k–$220k") == "$180k–$220k"  # non-numeric passes through
    assert format_url("github.com/alex") == "https://github.com/alex"


# --------------------------------------------------------------- name & contact
def test_first_last_name_split():
    actions = one([fld("f0-0", label="First Name"), fld("f0-1", label="Last Name")])
    assert actions[0]["op"] == "fill" and actions[0]["value"] == "Alex"
    assert actions[1]["op"] == "fill" and actions[1]["value"] == "Candidate"


def test_full_name_fallback():
    (a,) = one(fld(label="Name"))
    assert a["value"] == "Alex Candidate"


def test_email_by_input_type_and_confirm():
    actions = one([fld("f0-0", kind="email", label="Email"),
                   fld("f0-1", label="Confirm email address")])
    assert [a["value"] for a in actions] == ["alex@example.com"] * 2


def test_phone_formatted_by_input_type():
    (a,) = one(fld(kind="tel", label="Phone number"))
    assert a["value"] == "(212) 555-0147"


def test_url_prefix_on_url_inputs():
    (a,) = one(fld(kind="url", label="LinkedIn profile"))
    assert a["value"] == "https://linkedin.com/in/alex"


# ----------------------------------------------------------- selects & yes/no
def test_state_select_from_location():
    options = [{"value": "", "text": "Select…"}, {"value": "NJ", "text": "New Jersey"},
               {"value": "NY", "text": "New York"}]
    (a,) = one(fld(kind="select", label="State", options=options))
    assert a["op"] == "select" and a["value"] == "New York" and a["opt_value"] == "NY"


def test_work_authorization_select_yes():
    options = [{"value": "", "text": "--"}, {"value": "1", "text": "Yes"},
               {"value": "0", "text": "No"}]
    (a,) = one(fld(kind="select", options=options,
                   label="Are you legally authorized to work in the United States?"))
    assert a["op"] == "select" and a["value"] == "Yes"


def test_sponsorship_radio_checks_no():
    question = "Will you now or in the future require sponsorship?"
    actions = one([
        fld("f0-0", kind="radio", label="Yes", question=question),
        fld("f0-1", kind="radio", label="No", question=question),
    ])
    assert len(actions) == 1
    assert actions[0] == {"af": "f0-1", "op": "check", "value": "No",
                          "field": "requires_sponsorship"}


def test_salary_and_how_heard():
    salary, heard = one([
        fld("f0-0", label="Desired salary"),
        fld("f0-1", label="How did you hear about this job?"),
    ])
    assert salary["value"] == "$200,000"
    assert heard["value"] == "Company careers page"


# ------------------------------------------------------------------- skipping
def test_eeo_questions_skipped():
    actions = one([
        fld("f0-0", kind="select", label="Gender", options=[{"value": "m", "text": "Male"}]),
        fld("f0-1", kind="select", label="Veteran status", options=[]),
        fld("f0-2", kind="select", label="Race/Ethnicity", options=[]),
    ])
    assert all(a["op"] == "skip" and "demographic" in a["note"] for a in actions)


def test_cover_letter_and_prefilled_skipped():
    cover, filled = one([
        fld("f0-0", kind="textarea", label="Cover letter"),
        fld("f0-1", kind="email", label="Email", value="already@there.com"),
    ])
    assert cover["op"] == "skip" and "cover letter" in cover["note"]
    assert filled["op"] == "skip" and filled["note"] == "already filled"


def test_unknown_field_skipped_not_guessed():
    (a,) = one(fld(label="Security clearance level"))
    assert a["op"] == "skip" and a["note"] == "no matching profile field"
    # Unknown choice questions produce no action at all — left for the user.
    assert one(fld(kind="radio", label="Yes", question="Have you worked here before?")) == []


def test_resume_upload():
    (a,) = one(fld(kind="file", label="Resume/CV"), resume_path="/data/resume.pdf")
    assert a["op"] == "upload" and a["value"] == "/data/resume.pdf"
    (b,) = one(fld(kind="file", label="Resume/CV"))  # no pdf available
    assert b["op"] == "skip"


def test_empty_profile_value_skipped():
    (a,) = one(fld(label="Portfolio URL"))
    assert a["op"] == "skip" and "empty" in a["note"]


# -------------------------------------------------------- description renderer
def test_description_structured():
    text = ("About the role\nBuild systems.\nRESPONSIBILITIES:\n"
            "• Design APIs\n• Own services\nWe offer great benefits.")
    html = str(description_html(text))
    assert "<h3>RESPONSIBILITIES</h3>" in html
    assert "<ul><li>Design APIs</li><li>Own services</li></ul>" in html
    assert "<p>Build systems.</p>" in html


def test_description_legacy_single_line():
    text = ("First sentence here. Second one follows. Third too. "
            "Fourth starts a new paragraph. Fifth. Sixth.")
    html = str(description_html(text))
    assert html.count("<p>") == 2  # grouped ~3 sentences per paragraph


def test_description_escapes_html():
    assert "<script>" not in str(description_html("<script>alert(1)</script> hello"))
