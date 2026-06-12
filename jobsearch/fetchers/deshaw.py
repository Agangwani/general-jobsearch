"""D. E. Shaw careers (deshaw.com) via rendered-DOM link extraction.

The site is largely static with no public jobs API; role links are scraped
from the careers listing. No posting dates are exposed, so roles score with
the configured unknown-age penalty.
"""

from __future__ import annotations

from ..models import Company, JobPosting

URL = "https://www.deshaw.com/careers/choose-your-path"
SELECTOR = "a[href*='/careers/']"


def parse_links(links: list[dict], company_name: str) -> list[JobPosting]:
    jobs = []
    seen = set()
    for link in links:
        href = (link.get("href") or "").split("?")[0]
        title = (link.get("text") or "").strip().split("\n")[0]
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
            source="deshaw",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    links = runtime.extract_links(URL, SELECTOR)
    jobs = parse_links(links, company.name)
    if not jobs:
        raise RuntimeError("no role links found on deshaw.com careers page")
    return jobs
