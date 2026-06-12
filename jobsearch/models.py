from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Company:
    name: str
    ats: str
    tags: list[str] = field(default_factory=list)
    careers_url: str = ""
    enabled: bool = True
    params: dict = field(default_factory=dict)


@dataclass
class JobPosting:
    company: str
    title: str
    location: str
    url: str
    job_id: str
    description: str = ""
    posted_at: Optional[datetime] = None
    source: str = ""
    fit_score: float = 0.0
    rank_score: float = 0.0
    cluster: int = -1
    is_new: bool = False
    # Why this job missed the strict filter (near-miss jobs only), e.g.
    # "UNLEVELED_TITLE" or "EXCLUDED_TRACK:frontend". Empty for full matches.
    filter_reason: str = ""
    # Claude-validation verdict: "verified" / "mismatch" / "stale" / "" (unchecked).
    validation: str = ""
    validation_note: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.company}:{self.job_id}"

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.posted_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        posted = self.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return max(0.0, (now - posted).total_seconds() / 86400.0)


@dataclass
class FetchError:
    company: str
    error: str
