from __future__ import annotations

import re

from .models import JobPosting

DEFAULT_TITLE_INCLUDE = [
    r"\bsenior\b.*\b(software|backend|platform|infrastructure|full[- ]?stack|cloud|distributed|data)\b.*\b(engineer|developer)\b",
    r"\bsoftware (development )?engineer\b.*\b(iii|iv|3|4|senior)\b",
    r"\bstaff\b.*\bsoftware\b.*\bengineer\b",
]
DEFAULT_TITLE_EXCLUDE = [
    r"\b(intern|internship|co-?op|new grad|university|campus)\b",
    r"\b(manager|director|vp|vice president|head of|principal)\b",
]
DEFAULT_LOCATIONS = ["new york", "nyc", "brooklyn", "manhattan"]
REMOTE_HINTS = ["remote - us", "remote, us", "us remote", "remote (us", "remote in us", "united states - remote", "remote - united states"]


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

    def matches(self, job: JobPosting) -> bool:
        return self.title_ok(job.title) and self.location_ok(job.location)

    def apply(self, jobs: list[JobPosting]) -> list[JobPosting]:
        return [job for job in jobs if self.matches(job)]
