"""Company-lead sources: generalized job boards mined for *who is hiring*.

The fetchers/ package answers "what jobs does company X have?". This package
answers the upstream question — "which companies belong in the registry for
THIS resume?" — by searching boards that span many employers and reducing
their postings to CompanyLead records (company name + role/location/URL
evidence). company_discovery.py then merges leads across sources, ranks them
against the resume, resolves each to its own ATS board (discover.py), and
writes the generated registry that load_registry merges under the curated
companies.yaml.

Source signature: fetch(session, ctx) -> list[CompanyLead], where ctx is the
dict company_discovery builds from settings (query, location, location_subs,
categories, max_pages). Sources raise SourceSkip when they can't run in this
environment (e.g. a missing API key) and any other exception on failure; the
orchestrator catches both per source so one dead aggregator never sinks a
discovery run.

Sources implemented here are keyless-or-free and ToS-friendly (documented
public APIs only). Directories that require scraping past bot protection
(LinkedIn, Wellfound, Built In) are deliberately absent — same policy as the
fetchers (see README and docs/design-company-discovery.md).
"""

from __future__ import annotations


class SourceSkip(Exception):
    """Source can't run in this environment (missing API key, …) — a skip,
    not an error: reported as such and never counted as a failure."""


from .adzuna import fetch as fetch_adzuna  # noqa: E402
from .ats_boards import fetch as fetch_ats_boards  # noqa: E402
from .hn_hiring import fetch as fetch_hn_hiring  # noqa: E402
from .remotive import fetch as fetch_remotive  # noqa: E402
from .themuse import fetch as fetch_themuse  # noqa: E402
from .ycombinator import fetch as fetch_ycombinator  # noqa: E402

SOURCES = {
    "themuse": fetch_themuse,
    "hn_hiring": fetch_hn_hiring,
    "adzuna": fetch_adzuna,
    "ycombinator": fetch_ycombinator,
    "ats_boards": fetch_ats_boards,
    "remotive": fetch_remotive,
}
