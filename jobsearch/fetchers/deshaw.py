"""D. E. Shaw careers (deshaw.com) via rendered-DOM link extraction.

The site is largely static with no public jobs API; role links are scraped
from the careers listing. No posting dates are exposed, so roles score with
the configured unknown-age penalty.
"""

from __future__ import annotations

import re

from ..models import Company, JobPosting

URL = "https://www.deshaw.com/careers/choose-your-path"
SELECTOR = "a[href*='/careers/']"

_ENGINEERISH = re.compile(r"\b(engineer|developer|swe)\b", re.I)


def clean_title(raw: str) -> tuple[str, str]:
    """Rendered card text concatenates icon glyph + category + title + blurb
    ("iconSystems: Senior Linux Engineer: The D. E. Shaw group seeks ...").
    Pick the segment that names the role; keep the rest as description."""
    text = re.sub(r"^icon\s*", "", (raw or "").strip().split("\n")[0], flags=re.I)
    parts = [p.strip() for p in text.split(": ") if p.strip()]
    if not parts:
        return "", ""
    title = next((p for p in parts if _ENGINEERISH.search(p)), parts[0])
    rest = " ".join(p for p in parts if p is not title)
    return title[:120], rest


def parse_links(links: list[dict], company_name: str) -> list[JobPosting]:
    jobs = []
    seen = set()
    for link in links:
        href = (link.get("href") or "").split("?")[0]
        title, blurb = clean_title(link.get("text") or "")
        # Role detail pages look like /careers/<role-slug>-<numeric-id>
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if not title or not slug or not slug[-1].isdigit() or href in seen:
            continue
        seen.add(href)
        jobs.append(JobPosting(
            company=company_name,
            title=title,
            location="New York",  # D. E. Shaw engineering is NYC-based
            url=href,
            job_id=slug,
            description=blurb,
            source="deshaw",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    links = runtime.extract_links(URL, SELECTOR)
    jobs = parse_links(links, company.name)
    if not jobs:
        raise RuntimeError("no role links found on deshaw.com careers page")
    return jobs
