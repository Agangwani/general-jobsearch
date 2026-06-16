"""Auto-fill engine tests: pure plan() logic over field descriptors, value
formatting, and the description formatter. No browser needed."""

from webapp.autofill import (
    _enrich_with_schema, format_phone, format_salary, format_url, merge_resume,
    parse_location, plan, split_name,
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
def test_eeo_skipped_when_profile_has_no_value():
    # PROFILE carries no demographic values, so EEO selects are skipped, never guessed.
    actions = one([
        fld("f0-0", kind="select", label="Gender", options=[{"value": "m", "text": "Male"}]),
        fld("f0-1", kind="select", label="Veteran status", options=[]),
        fld("f0-2", kind="select", label="Race/Ethnicity", options=[]),
    ])
    assert all(a["op"] == "skip" for a in actions)


def test_demographic_filled_when_set():
    profile = {**PROFILE, "gender": "Male", "race_ethnicity": "Asian"}
    (g,) = plan([fld(kind="select", label="Gender",
                     options=[{"value": "m", "text": "Male"}, {"value": "f", "text": "Female"}])], profile)
    assert g["op"] == "select" and g["value"] == "Male"
    (r,) = plan([fld(kind="select", label="Race / Ethnicity",
                     options=[{"value": "a", "text": "Asian (Not Hispanic or Latino)"}])], profile)
    assert r["op"] == "select" and "Asian" in r["value"]


def test_demographic_decline_matches_any_wording():
    # "Decline" is matched by intent — works across ATSs that phrase it differently.
    profile = {**PROFILE, "disability_status": "Decline to self-identify"}
    opts = [{"value": "1", "text": "Yes, I have a disability"},
            {"value": "2", "text": "No, I do not have a disability"},
            {"value": "3", "text": "I do not wish to answer"}]
    (a,) = plan([fld(kind="select", label="Disability Status", options=opts)], profile)
    assert a["op"] == "select" and a["value"] == "I do not wish to answer"


def test_cover_letter_filled_from_profile():
    profile = {**PROFILE, "cover_letter": "Dear team, I'm excited to apply."}
    (a,) = plan([fld(kind="textarea", label="Cover Letter")], profile)
    assert a["op"] == "fill" and a["value"].startswith("Dear team")
    # A cover-letter *file* input is never synthesised.
    (b,) = plan([fld(kind="file", label="Cover Letter")], profile)
    assert b["op"] == "skip"


def test_education_and_address_filled_from_profile():
    profile = {**PROFILE, "school": "NYU", "degree": "BS", "discipline": "Computer Science",
               "street_address": "1 Main St", "postal_code": "10001", "country": "United States"}
    fields = [fld("f0-0", label="School"), fld("f0-1", label="Degree"),
              fld("f0-2", label="Discipline"), fld("f0-3", label="Street Address"),
              fld("f0-4", label="Zip / Postal code"), fld("f0-5", label="Country")]
    got = {a["field"]: a["value"] for a in plan(fields, profile) if a["op"] == "fill"}
    assert got == {"school": "NYU", "degree": "BS", "discipline": "Computer Science",
                   "street_address": "1 Main St", "postal_code": "10001", "country": "United States"}


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


# -------------------------------------------------- custom dropdowns (combobox)
def test_combobox_yesno_with_known_options():
    options = [{"value": "1", "text": "Yes"}, {"value": "0", "text": "No"}]
    (a,) = one(fld(kind="combobox", options=options,
                   question="Are you legally authorized to work in the US?"))
    assert a["op"] == "select" and a["value"] == "Yes" and a["combo"] is True


def test_combobox_yesno_options_not_yet_rendered():
    # A React combobox exposes no options until opened — plan() still emits a
    # combo action carrying the wanted answer for the executor to match live.
    (a,) = one(fld(kind="combobox",
                   question="Will you require visa sponsorship?"))
    assert a["op"] == "select" and a["value"] == "No" and a["combo"] is True


def test_combobox_how_heard_defers_to_live_options():
    (a,) = one(fld(kind="combobox", label="How did you hear about this role?"))
    assert a["op"] == "select" and a["combo"] is True and a["how_heard"] is True


def test_combobox_blocks_identity_but_allows_education():
    # A phone-country combobox (matches "phone") is left for the user, not mistyped.
    (a,) = one(fld(kind="combobox", question="Phone"))
    assert a["op"] == "skip" and "dropdown" in a["note"]
    # A school combobox is filled from the profile (executor does the live typeahead).
    (b,) = plan([fld(kind="combobox", label="School")], {**PROFILE, "school": "NYU"})
    assert b["op"] == "select" and b["combo"] is True and b["value"] == "NYU"


def test_native_select_is_not_combo():
    options = [{"value": "1", "text": "Yes"}, {"value": "0", "text": "No"}]
    (a,) = one(fld(kind="select", options=options,
                   label="Are you legally authorized to work in the US?"))
    assert a["op"] == "select" and a.get("combo") is not True


# ------------------------------------------------ greenhouse schema enrichment
def test_schema_marks_plain_input_as_dropdown():
    # Greenhouse renders this select as a bare <input> (kind 'text'); the schema
    # tells us it's really a Yes/No dropdown, so we answer instead of skipping.
    fields = [fld(kind="text", name="job_application[question_555]",
                  label="Are you legally authorized to work in the US?")]
    schema = {"question_555": {
        "label": "Are you legally authorized to work in the US?",
        "required": True, "type": "multi_value_single_select",
        "options": [{"value": "1", "text": "Yes"}, {"value": "0", "text": "No"}]}}
    _enrich_with_schema(fields, schema)
    assert fields[0]["schema_select"] is True
    assert fields[0]["options"][0]["text"] == "Yes"
    (a,) = plan(fields, PROFILE)
    assert a["op"] == "select" and a["value"] == "Yes" and a["combo"] is True


def test_schema_leaves_unrelated_fields_alone():
    fields = [fld(kind="text", name="job_application[first_name]", label="First Name")]
    _enrich_with_schema(fields, {"first_name": {
        "label": "First Name", "required": True, "type": "input_text", "options": []}})
    assert "schema_select" not in fields[0]
    (a,) = plan(fields, PROFILE)
    assert a["op"] == "fill" and a["value"] == "Alex"


# ----------------------------------------------------------- resume fallback
def test_merge_resume_profile_wins_resume_fills_gaps():
    profile = {"full_name": "Alex Candidate", "location": "", "current_company": "Capital One"}
    resume = {"full_name": "Resume Name", "location": "New York, NY", "school": "PSU"}
    m = merge_resume(profile, resume)
    assert m["full_name"] == "Alex Candidate"      # set profile value wins
    assert m["location"] == "New York, NY"         # blank profile → resume fills
    assert m["current_company"] == "Capital One"   # profile-only retained
    assert m["school"] == "PSU"                     # resume-only added
    assert merge_resume(profile, None) is profile  # no resume → unchanged


def test_resume_fallback_fills_empty_profile_field():
    merged = merge_resume({**PROFILE, "location": ""}, {"location": "Austin, TX"})
    (a,) = plan([fld(label="Location")], merged)
    assert a["op"] == "fill" and a["value"] == "Austin, TX"


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
