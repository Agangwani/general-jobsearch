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

    def matches(self, job: JobPosting) -> bool:
        return self.title_ok(job.title) and self.location_ok(job.location)

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
                return NEAR_LOCATION, "REMOTE_ONLY"
            return OUT, ""

        # Title failed. Only NYC-located engineering roles qualify as near-misses.
        if not loc_ok or not job.title or not ENGINEERISH.search(job.title):
            return OUT, ""
        if HARD_EXCLUDE.search(job.title):
            return OUT, ""
        hit = next((p for p in self.exclude if p.search(job.title)), None)
        if hit:
            word = hit.search(job.title).group(0).lower()
            return NEAR_TITLE, f"EXCLUDED_TRACK:{word}"
        if not SENIORITY_MARKER.search(job.title):
            if SENIOR_YEARS.search(job.description or ""):
                return NEAR_TITLE, "UNLEVELED_TITLE"  # e.g. Stripe posts no levels
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
