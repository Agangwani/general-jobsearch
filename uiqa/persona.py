"""A simulated user — the resume + the realistic values they'd type into forms.

The explorer drives the UI *as this persona*: its resume seeds the app's
role-targeting and profile, and `value_for()` answers "what would this person
put in this field?" so form fills look like a real applicant rather than
`test123` noise. Default persona reads the repo's bundled sample resume so a
run needs zero setup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Realistic profile values for the default persona. Mirrors the field names the
# app's profile/autofill use (see webapp/profile.py FIELD_OPTIONS) so seeded
# values are valid, not rejected.
_DEFAULT_PROFILE = {
    "full_name": "Avery Quinn",
    "email": "avery.quinn.dev@example.com",
    "phone": "555-0142",
    "location": "Brooklyn, NY",
    "linkedin": "linkedin.com/in/averyquinn",
    "github": "github.com/averyquinn",
    "website": "averyquinn.dev",
    "current_company": "Northwind Labs",
    "current_title": "Senior Software Engineer",
    "school": "Hunter College",
    "degree": "Bachelor's Degree",
    "discipline": "Computer Science",
    "grad_year": "2016",
    "years_experience": "8",
    "work_authorization": "Yes",
    "requires_sponsorship": "No",
    "gender": "Decline to self-identify",
    "race": "Decline to self-identify",
    "veteran_status": "Decline to self-identify",
    "disability_status": "Decline to self-identify",
    "street_address": "55 Water St",
    "city": "Brooklyn",
    "state": "NY",
    "zip": "11201",
}

_DEFAULT_RESUME = """Avery Quinn
avery.quinn.dev@example.com | 555-0142 | github.com/averyquinn | linkedin.com/in/averyquinn
Brooklyn, NY

SUMMARY
Senior Software Engineer with 8 years building backend services and developer
platforms. Python, Go, distributed systems, Kubernetes, AWS, payments, and
high-throughput APIs.

EXPERIENCE
Northwind Labs, New York, NY
Senior Software Engineer  Jan 2021 - Present
- Led the migration of the billing platform to event-driven services.
- Cut p99 latency 40% on the core payments API.

Globex, New York, NY
Software Engineer  2016 - 2021
- Built internal tooling and CI/CD for a 60-engineer org.

EDUCATION
Hunter College, New York, NY
B.S. Computer Science, 2016

SKILLS
Python, Go, PostgreSQL, Kafka, Kubernetes, AWS, Terraform, distributed systems,
payments, API design.
"""


@dataclass
class Persona:
    """The user the harness simulates. `name` keys the run; `resume_text` seeds
    role targeting; `profile` answers form fields."""

    name: str = "sample"
    resume_text: str = _DEFAULT_RESUME
    profile: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_PROFILE))

    # Free-text the persona might type into a search box, smallest-effort first.
    search_terms: tuple[str, ...] = ("engineer", "senior", "python", "")

    @classmethod
    def load(cls, root: Path, name: str = "sample") -> "Persona":
        """Built-in personas plus a `file:<path>` / `<name>` lookup under
        data/personas/. Falls back to the bundled sample resume."""
        if name.startswith("file:"):
            text = Path(name[5:]).read_text()
            return cls(name=Path(name[5:]).stem, resume_text=text)
        custom = root / "data" / "personas" / f"{name}.json"
        if custom.exists():
            raw = json.loads(custom.read_text())
            p = cls(name=name, resume_text=raw.get("resume_text", _DEFAULT_RESUME))
            p.profile.update(raw.get("profile", {}))
            return p
        if name == "sample":
            sample = root / "data" / "sample_resume.txt"
            if sample.exists():
                return cls(name="sample", resume_text=sample.read_text())
        return cls(name=name)

    def value_for(self, *, name: str = "", input_type: str = "text",
                  placeholder: str = "", label: str = "") -> str:
        """The value this persona would enter into a field, inferred from its
        name/type/placeholder/label. Used to fill arbitrary forms realistically."""
        hay = " ".join((name, placeholder, label)).lower()
        t = (input_type or "text").lower()

        if t == "email" or "email" in hay:
            return self.profile["email"]
        if t == "tel" or "phone" in hay:
            return self.profile["phone"]
        if t == "url" or "website" in hay or "portfolio" in hay:
            return self.profile["website"]
        if t == "number":
            # Stay inside any explicit min/max the caller already validated; a
            # neutral mid value avoids tripping required-range checks.
            return "5"
        if t in ("date",):
            return "2026-01-01"
        if "linkedin" in hay:
            return self.profile["linkedin"]
        if "github" in hay:
            return self.profile["github"]
        if "name" in hay:
            return self.profile["full_name"]
        if "company" in hay:
            return self.profile["current_company"]
        if "title" in hay or "role" in hay:
            return self.profile["current_title"]
        if "school" in hay or "university" in hay:
            return self.profile["school"]
        if "city" in hay:
            return self.profile["city"]
        if "state" in hay:
            return self.profile["state"]
        if "zip" in hay or "postal" in hay:
            return self.profile["zip"]
        if "address" in hay:
            return self.profile["street_address"]
        if t == "search" or "search" in hay or "filter" in hay:
            return self.search_terms[0]
        if "note" in hay or "cover" in hay or "message" in hay:
            return "Excited about this role — strong fit with my backend background."
        return self.profile["full_name"]
