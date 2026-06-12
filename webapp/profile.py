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

# Field order defines the copy-paste panel layout.
STANDARD_FIELDS = [
    "full_name", "email", "phone", "location", "linkedin", "github",
    "portfolio", "current_title", "current_company", "years_experience",
    "work_authorization", "requires_sponsorship", "salary_expectation",
    "notice_period", "preferred_pronouns",
]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.I)
_GITHUB = re.compile(r"github\.com/[\w-]+", re.I)


def seed_from_resume(resume_text: str) -> dict[str, str]:
    """Best-effort extraction; everything is editable in the UI afterwards."""
    lines = [l.strip() for l in resume_text.splitlines() if l.strip()]
    fields: dict[str, str] = {}
    if lines:
        fields["full_name"] = lines[0][:80]
    if len(lines) > 1 and "," in lines[1]:
        title_part = lines[1].split(",")[0].strip()
        fields["current_title"] = title_part
        fields["location"] = ",".join(lines[1].split(",")[1:]).strip()
    head = resume_text[:2000]
    for pattern, field in ((_EMAIL, "email"), (_PHONE, "phone"),
                           (_LINKEDIN, "linkedin"), (_GITHUB, "github")):
        match = pattern.search(head)
        if match:
            fields[field] = match.group(0)
    return fields


def ensure_seeded(conn, root: Path) -> None:
    existing = conn.execute("SELECT COUNT(*) AS n FROM profile_fields").fetchone()["n"]
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
    for field in STANDARD_FIELDS:
        conn.execute(
            "INSERT OR IGNORE INTO profile_fields (field, value, updated_at) VALUES (?, ?, ?)",
            (field, seeded.get(field, ""), now),
        )
    conn.commit()


def all_fields(conn) -> list:
    rows = conn.execute("SELECT * FROM profile_fields").fetchall()
    order = {f: i for i, f in enumerate(STANDARD_FIELDS)}
    return sorted(rows, key=lambda r: order.get(r["field"], 99))


def set_field(conn, field: str, value: str) -> None:
    conn.execute(
        "INSERT INTO profile_fields (field, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(field) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (field, value, db.utcnow()),
    )
    conn.commit()


def reseed_from_resume(conn, resume_text: str) -> None:
    """Refresh the resume-derived fields after a new upload. Only fields the
    parser actually extracted are overwritten; everything else (work auth,
    salary expectation, manual edits to untouched fields) is preserved."""
    for field, value in seed_from_resume(resume_text).items():
        set_field(conn, field, value)
