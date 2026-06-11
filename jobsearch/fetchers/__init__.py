"""Fetcher registry: maps the `ats` field in companies.yaml to a fetch function.

Every fetcher has the signature fetch(company, session, settings) -> list[JobPosting]
and raises on failure; the pipeline catches per-company errors so one broken
board never sinks the daily run.
"""

from . import (
    amazon,
    apple,
    ashby,
    bloomberg,
    eightfold,
    google,
    greenhouse,
    lever,
    meta,
    microsoft,
    spotify,
    uber,
    workday,
)

FETCHERS = {
    "amazon": amazon.fetch,
    "apple": apple.fetch,
    "ashby": ashby.fetch,
    "bloomberg": bloomberg.fetch,
    "eightfold": eightfold.fetch,
    "google": google.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "meta": meta.fetch,
    "microsoft": microsoft.fetch,
    "spotify": spotify.fetch,
    "uber": uber.fetch,
    "workday": workday.fetch,
}
