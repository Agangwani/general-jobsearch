from __future__ import annotations

import re

from .models import JobPosting

DEFAULT_TITLE_INCLUDE = [
    r"\b(senior|sr)\b.*\b(software|backend|platform|infrastructure|full[- ]?stack|cloud|distributed|data)\b.*\b(engineer|developer)\b",
    r"\bsoftware (development )?engineer\b.*\b(iii|iv|3|4|senior)\b",
    r"\bstaff\b.*\bsoftware\b.*\bengineer\b",
]
DEFAULT_TITLE_EXCLUDE = [
    r"\b(intern|internship|co-?op|new grad|university|campus)\b",
    r"\b(manager|director|vp|vice president|head of|principal)\b",
]
DEFAULT_LOCATIONS = ["new york", "nyc", "brooklyn", "manhattan"]
REMOTE_HINTS = [
    "remote - us", "remote, us", "us remote", "remote (us", "remote in us",
    "united states - remote", "remote - united states", "remote us",
    "remote, united states", "united states remote", "us - remote",
    "us-remote", "remote-us", "remote within the us", "remote (within the us",
    "remote-first", "fully remote",
]

# Hard exclusions: never a near-miss, a different career stage entirely.
HARD_EXCLUDE = re.compile(
    r"\b(intern|internship|co-?op|new grad|university|campus|apprentice"
    r"|manager|director|vp|vice president|head of|principal|distinguished|fellow)\b",
    re.I,
)
ENGINEERISH = re.compile(r"\b(engineer|developer|swe)\b", re.I)
SENIORITY_MARKER = re.compile(r"\b(senior|sr|staff|lead|iii|iv|[34])\b", re.I)
MID_LEVEL = re.compile(r"\b(ii|2)\b", re.I)
# "5+ years", "7 years", "10+ years" in the description ⇒ effectively senior.
SENIOR_YEARS = re.compile(r"\b([5-9]|1[0-5])\s*\+?\s*years?\b", re.I)
# Guard for unleveled-title promotion: the title itself must look like a
# software role, not just any engineer (no promoting "Network Engineer").
SOFTWAREISH = re.compile(
    r"\b(software|backend|back[- ]end|platform|infrastructure|full[- ]?stack"
    r"|cloud|distributed|data|payments|machine learning|ml|swe|developer)\b", re.I)

_PAY_FULL = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d{5,7})(?:\.\d+)?\b")  # $187,500 / $187500
_PAY_K = re.compile(r"\$\s*(\d{2,3}(?:\.\d+)?)\s*[kK]\b")                  # $187.5K


def extract_max_pay(text: str) -> int | None:
    """Top end of any USD pay figure in the text (NYC/CO/CA/WA transparency
    ranges). None when nothing looks like a plausible annual salary — hourly
    rates and stray small numbers fall outside the plausibility band."""
    if not text or "$" not in text:
        return None
    amounts = [int(m.group(1).replace(",", "")) for m in _PAY_FULL.finditer(text)]
    amounts += [int(float(m.group(1)) * 1000) for m in _PAY_K.finditer(text)]
    plausible = [a for a in amounts if 40_000 <= a <= 2_000_000]
    return max(plausible) if plausible else None

# Classification statuses
MATCH = "match"
NEAR_TITLE = "near_title"        # engineering role in NYC that failed the title filter
NEAR_LOCATION = "near_location"  # title matched but the role is US-remote
OUT = "out"


class JobFilter:
    def __init__(self, search_settings: dict):
        include = search_settings.get("title_include") or DEFAULT_TITLE_INCLUDE
        exclude = search_settings.get("title_exclude") or DEFAULT_TITLE_EXCLUDE
        self.include = [re.compile(p, re.I) for p in include]
        self.exclude = [re.compile(p, re.I) for p in exclude]
        self.locations = [loc.lower() for loc in (search_settings.get("locations") or DEFAULT_LOCATIONS)]
        self.include_remote = bool(search_settings.get("include_remote", False))
        # Remote-US roles enter the main table when the posting shows a pay
        # range topping out at/above this floor (USD/yr). 0 disables.
        self.remote_min_pay = int(search_settings.get("remote_min_pay", 0) or 0)
        # Promote unleveled titles (no level in title, 5+ years required in
        # the description) into the main table — Stripe/OpenAI/Jane Street.
        self.promote_unleveled = bool(search_settings.get("promote_unleveled", False))

    def title_ok(self, title: str) -> bool:
        if not title:
            return False
        if any(p.search(title) for p in self.exclude):
            return False
        return any(p.search(title) for p in self.include)

    def location_ok(self, location: str) -> bool:
        loc = (location or "").lower()
        if any(sub in loc for sub in self.locations):
            return True
        if self.include_remote and any(hint in loc for hint in REMOTE_HINTS):
            return True
        return False

    def is_remote_us(self, location: str) -> bool:
        loc = (location or "").lower()
        return any(hint in loc for hint in REMOTE_HINTS)

    def _remote_pay_ok(self, job: JobPosting) -> bool:
        """The remote carve-out: a US-remote role whose posted pay range tops
        out at/above the floor counts as location-acceptable."""
        if not self.remote_min_pay or not self.is_remote_us(job.location):
            return False
        pay = extract_max_pay(job.description or "")
        return pay is not None and pay >= self.remote_min_pay

    def matches(self, job: JobPosting) -> bool:
        return self.classify(job)[0] == MATCH

    def classify(self, job: JobPosting) -> tuple[str, str]:
        """Classify a job as (status, reason) instead of a bare boolean, so the
        report can show *why* near-misses missed (see
        docs/analysis-zero-match-companies.md#near-miss-report)."""
        title_ok = self.title_ok(job.title)
        loc_ok = self.location_ok(job.location)

        if title_ok and loc_ok:
            return MATCH, ""
        if title_ok and not loc_ok:
            if self.is_remote_us(job.location):
                if self._remote_pay_ok(job):
                    return MATCH, ""
                if self.remote_min_pay:
                    pay = extract_max_pay(job.description or "")
                    return NEAR_LOCATION, (
                        "REMOTE_PAY_BELOW_MIN" if pay else "REMOTE_NO_PAY_RANGE")
                return NEAR_LOCATION, "REMOTE_ONLY"
            return OUT, ""

        # Title failed. Near-misses must be location-acceptable engineering
        # roles: NYC, or US-remote clearing the pay floor.
        if not (loc_ok or self._remote_pay_ok(job)) or not job.title \
                or not ENGINEERISH.search(job.title):
            return OUT, ""
        if HARD_EXCLUDE.search(job.title):
            return OUT, ""
        hit = next((p for p in self.exclude if p.search(job.title)), None)
        if hit:
            word = hit.search(job.title).group(0).lower()
            return NEAR_TITLE, f"EXCLUDED_TRACK:{word}"
        if not SENIORITY_MARKER.search(job.title):
            if SENIOR_YEARS.search(job.description or ""):
                if self.promote_unleveled and SOFTWAREISH.search(job.title):
                    return MATCH, ""  # e.g. Stripe posts no levels — promoted
                return NEAR_TITLE, "UNLEVELED_TITLE"
            if MID_LEVEL.search(job.title):
                return NEAR_TITLE, "MID_LEVEL"
            return NEAR_TITLE, "UNLEVELED_TITLE_UNVERIFIED"
        return NEAR_TITLE, "OTHER_ENG_TRACK"  # e.g. Senior SRE / DevOps / Solutions

    def apply(self, jobs: list[JobPosting]) -> list[JobPosting]:
        return [job for job in jobs if self.matches(job)]


def build_funnel(
    jobs: list[JobPosting], job_filter: JobFilter, max_age_days: float = 0
) -> dict[str, dict[str, int]]:
    """Per-company counts: fetched → title_pass → loc_pass → matched / near_miss.
    One look at this table settles 'no jobs vs. can't see them'.

    matched/near_miss respect `max_age_days` (when nonzero) so they agree with
    what the report can actually show; fetched/title/loc stay raw."""
    funnel: dict[str, dict[str, int]] = {}
    for job in jobs:
        row = funnel.setdefault(
            job.company,
            {"fetched": 0, "title_pass": 0, "loc_pass": 0, "matched": 0, "near_miss": 0, "aged_out": 0},
        )
        row["fetched"] += 1
        title_ok = job_filter.title_ok(job.title)
        loc_ok = job_filter.location_ok(job.location)
        row["title_pass"] += title_ok
        row["loc_pass"] += loc_ok
        status, _ = job_filter.classify(job)
        if status == OUT:
            continue
        if max_age_days and (job.age_days() or 0) > max_age_days:
            row["aged_out"] += 1
        elif status == MATCH:
            row["matched"] += 1
        else:
            row["near_miss"] += 1
    return funnel
