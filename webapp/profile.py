"""Profile fields: the user's preloaded application data.

Seeded on first launch from data/profile.yaml (if present) and best-effort
parsing of data/resume.txt, then editable in the UI. These power the
copy-paste panel on every job page and, later, automated form prefill
(docs/design-application-automation.md Stage 2). Values live only in the
local database — never in the repo.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import db

# Field order defines the copy-paste panel layout and the profile page.
STANDARD_FIELDS = [
    "full_name", "email", "phone", "location", "linkedin", "github",
    "portfolio", "current_title", "current_company", "years_experience",
    "work_authorization", "requires_sponsorship", "salary_expectation",
    "notice_period", "preferred_pronouns",
    # Address & education — filled into application forms when present.
    "street_address", "postal_code", "country",
    "school", "degree", "discipline", "graduation_year",
    # Voluntary self-identification (EEO). Blank = skipped, never guessed; set
    # an answer (e.g. "Decline to self-identify") to have it filled for you.
    "gender", "race_ethnicity", "veteran_status", "disability_status",
    # Optional default cover letter (rendered as a textarea on the profile page).
    "cover_letter",
]

# Fields the user is unlikely to want preloaded into the copy-paste panel — they
# exist for form auto-fill but are hidden from the per-job panel to keep it tight.
AUTOFILL_ONLY_FIELDS = {
    "street_address", "postal_code", "country", "school", "degree", "discipline",
    "graduation_year", "gender", "race_ethnicity", "veteran_status",
    "disability_status", "cover_letter",
}

# Curated dropdown choices for fields whose application-form values are
# standardised. Derived from sampling ~100 live job postings (Greenhouse). The
# stored value is matched against each form's own options at fill time, so the
# wording here just needs to be close — "Decline to self-identify" in particular
# resolves to whatever a given form calls it (see autofill.DECLINE_RE).
FIELD_OPTIONS: dict[str, list[str]] = {
    "work_authorization": ["Yes, authorized to work", "No, not authorized"],
    "requires_sponsorship": ["No", "Yes"],
    "degree": ["High School Diploma", "Associate's Degree", "Bachelor's Degree",
               "Master's Degree", "Doctorate (PhD)", "MBA", "Other"],
    "gender": ["Male", "Female", "Non-binary", "Decline to self-identify"],
    "race_ethnicity": [
        "American Indian or Alaska Native", "Asian", "Black or African American",
        "Hispanic or Latino", "Native Hawaiian or Other Pacific Islander", "White",
        "Two or More Races", "Decline to self-identify"],
    "veteran_status": [
        "I am not a protected veteran",
        "I identify as one or more of the classifications of a protected veteran",
        "Decline to self-identify"],
    "disability_status": [
        "No, I do not have a disability",
        "Yes, I have a disability (or previously had one)",
        "Decline to self-identify"],
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.I)
_GITHUB = re.compile(r"github\.com/[\w-]+", re.I)
# "City, ST" — a single-word city, OR a two-word city only when the first word
# is a known multi-word-city prefix (New York, San Francisco, …). This stops the
# match from greedily eating a company name's last word ("Acme Corp Austin, TX"
# → "Austin", not "Corp Austin") while still catching real two-word cities.
_LOCATION = re.compile(
    r"\b((?:New|San|Los|Las|Saint|St\.?|Fort|Ft\.?|Salt|Santa|Palo|Mount) "
    r"[A-Z][A-Za-z.]+|[A-Z][A-Za-z.]+),\s*([A-Z]{2})\b")
_DEGREE = re.compile(
    r"\b(Ph\.?\s?D|Doctor(?:ate)?|MBA|M\.?\s?S\.?|M\.?\s?A\.?|Master(?:'s)?"
    r"|B\.?\s?S\.?|B\.?\s?A\.?|Bachelor(?:'s)?|Associate(?:'s)?)\b", re.I)
_DEGREE_CANON = [
    (re.compile(r"ph\.?\s?d|doctor", re.I), "Doctorate (PhD)"),
    (re.compile(r"mba", re.I), "MBA"),
    (re.compile(r"m\.?\s?s\.?|m\.?\s?a\.?|master", re.I), "Master's Degree"),
    (re.compile(r"b\.?\s?s\.?|b\.?\s?a\.?|bachelor", re.I), "Bachelor's Degree"),
    (re.compile(r"associate", re.I), "Associate's Degree"),
]
_DATE_START = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{4}"
    r"|\b(19|20)\d{2}\b|\b(present|current)\b", re.I)


# PDF→text extraction often injects stray spaces inside header words
# ("RELEV ANT EXPERIENCE"), so match against the letters-only collapse of a
# short line, anchored so content lines like "Experienced developer" don't match.
_SECTION_PATTERNS = [
    ("experience", re.compile(r"^(relevant|work|professional)?experiences?$")),
    ("education", re.compile(r"^educations?$")),
    ("skills", re.compile(r"^(technical)?skills.*$")),
    ("projects", re.compile(r"^(key|technical|personal)?projects?$")),
    ("certification", re.compile(r"^certifications?.*$")),
]


def _section_key(line: str) -> str | None:
    """Canonical section name if `line` is a short section header, else None."""
    if len(line) > 30:
        return None
    collapsed = re.sub(r"[^a-z]", "", line.lower())
    for key, rx in _SECTION_PATTERNS:
        if rx.match(collapsed):
            return key
    return None


def _sections(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        key = _section_key(line)
        if key:
            current = key
            out.setdefault(key, [])
        elif current:
            out[current].append(line)
    return out


def _canon_degree(text: str) -> str:
    for rx, canon in _DEGREE_CANON:
        if rx.search(text):
            return canon
    return ""


def _strip_dates(line: str) -> str:
    match = _DATE_START.search(line)
    return (line[:match.start()] if match else line).strip(" -–—•·\t")


def seed_from_resume(resume_text: str) -> dict[str, str]:
    """Best-effort extraction of profile fields from resume text. Heuristic and
    format-dependent; everything is editable in the UI afterwards."""
    lines = [l.strip() for l in resume_text.splitlines() if l.strip()]
    fields: dict[str, str] = {}
    if lines:
        fields["full_name"] = lines[0][:80]

    head = resume_text[:2000]
    for pattern, field in ((_EMAIL, "email"), (_PHONE, "phone"),
                           (_LINKEDIN, "linkedin"), (_GITHUB, "github")):
        match = pattern.search(head)
        if match:
            fields[field] = match.group(0)

    sections = _sections(lines)
    exp = sections.get("experience", [])
    if exp:
        loc = _LOCATION.search(exp[0])
        if loc:
            fields["location"] = f"{loc.group(1)}, {loc.group(2)}"
            company = exp[0][:loc.start()].strip(" ,-")
            if company:
                fields["current_company"] = company[:80]
        if len(exp) > 1:
            title = _strip_dates(exp[1])
            if title:
                fields["current_title"] = title[:80]

    edu = sections.get("education", [])
    if edu:
        loc = _LOCATION.search(edu[0])
        school = (edu[0][:loc.start()] if loc else edu[0]).split(",")[0].strip()
        if school:
            fields["school"] = school[:80]
        for dline in edu[1:3]:
            deg = _DEGREE.search(dline)
            if deg:
                fields["degree"] = _canon_degree(deg.group(0)) or deg.group(0)
                rest = re.sub(r"^(in|of)\s+", "", dline[deg.end():].strip(" .,"), flags=re.I)
                discipline = rest.split(",")[0].strip()
                if discipline:
                    fields["discipline"] = discipline[:60]
                break
    return fields


def populate_from_resume(conn, resume_text: str, *, only_empty: bool = True,
                         user_id: str = db.LOCAL_USER_ID) -> list[str]:
    """Fill profile fields from the resume. By default only fills blanks, so a
    user's manual edits are preserved. Returns the list of fields changed."""
    existing = {r["field"]: r["value"] for r in all_fields(conn, user_id)}
    changed = []
    for field, value in seed_from_resume(resume_text).items():
        if not value or (only_empty and existing.get(field)):
            continue
        set_field(conn, field, value, user_id=user_id)
        changed.append(field)
    return changed


def ensure_seeded(conn, root: Path, user_id: str = db.LOCAL_USER_ID) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM profile_fields WHERE user_id = ?",
        (user_id,)).fetchone()["n"]
    if existing:
        return
    seeded: dict[str, str] = {}
    profile_yaml = root / "data" / "profile.yaml"
    if profile_yaml.exists():
        import yaml
        loaded = yaml.safe_load(profile_yaml.read_text()) or {}
        seeded.update({k: str(v) for k, v in loaded.items() if v is not None})
    resume = root / "data" / "resume.txt"
    if resume.exists():
        for field, value in seed_from_resume(resume.read_text()).items():
            seeded.setdefault(field, value)
    now = db.utcnow()
    # No rows for this user yet (checked above), so a plain insert per field is safe.
    for field in STANDARD_FIELDS:
        conn.execute(
            "INSERT INTO profile_fields (user_id, field, value, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, field, seeded.get(field, ""), now),
        )
    conn.commit()


def ensure_fields(conn, user_id: str = db.LOCAL_USER_ID) -> None:
    """Top up any STANDARD_FIELDS missing for this user (idempotent), so
    newly-added profile fields show up without disturbing already-saved values."""
    now = db.utcnow()
    have = {r["field"] for r in conn.execute(
        "SELECT field FROM profile_fields WHERE user_id = ?", (user_id,)).fetchall()}
    for field in STANDARD_FIELDS:
        if field not in have:
            conn.execute(
                "INSERT INTO profile_fields (user_id, field, value, updated_at) "
                "VALUES (?, ?, ?, ?)", (user_id, field, "", now))
    conn.commit()


def all_fields(conn, user_id: str = db.LOCAL_USER_ID) -> list:
    rows = conn.execute(
        "SELECT * FROM profile_fields WHERE user_id = ?", (user_id,)).fetchall()
    order = {f: i for i, f in enumerate(STANDARD_FIELDS)}
    return sorted(rows, key=lambda r: order.get(r["field"], 99))


def panel_fields(conn, user_id: str = db.LOCAL_USER_ID) -> list:
    """Rows for the per-job copy-paste panel — the core contact fields only,
    without the form-fill extras (address/education/EEO/cover letter)."""
    return [r for r in all_fields(conn, user_id)
            if r["field"] not in AUTOFILL_ONLY_FIELDS]


def set_field(conn, field: str, value: str, user_id: str = db.LOCAL_USER_ID) -> None:
    # Explicit upsert scoped by (user_id, field) — avoids depending on a
    # particular UNIQUE constraint, so it works on both fresh (composite-unique)
    # and migrated single-user databases.
    now = db.utcnow()
    row = conn.execute(
        "SELECT id FROM profile_fields WHERE user_id = ? AND field = ?",
        (user_id, field)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO profile_fields (user_id, field, value, updated_at) "
            "VALUES (?, ?, ?, ?)", (user_id, field, value, now))
    else:
        conn.execute(
            "UPDATE profile_fields SET value = ?, updated_at = ? WHERE id = ?",
            (value, now, row["id"]))
    conn.commit()


def reseed_from_resume(conn, resume_text: str,
                       user_id: str = db.LOCAL_USER_ID) -> None:
    """Refresh the resume-derived fields after a new upload. Only fields the
    parser actually extracted are overwritten; everything else (work auth,
    salary expectation, manual edits to untouched fields) is preserved."""
    for field, value in seed_from_resume(resume_text).items():
        set_field(conn, field, value, user_id=user_id)
