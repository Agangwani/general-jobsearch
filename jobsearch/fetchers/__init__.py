"""Fetcher registries: map the `ats` field in companies.yaml to a fetch function.

FETCHERS hold plain HTTP/API fetchers with the signature
fetch(company, session, settings) -> list[JobPosting].

BROWSER_FETCHERS hold headless-Chromium fetchers with the signature
fetch(company, runtime, settings) -> list[JobPosting]; they run sequentially
after the API pass, sharing one BrowserRuntime. A company can also name one
as `fallback:` to retry through the browser when its API fetcher breaks.

All fetchers raise on failure; the pipeline catches per-company errors so one
broken board never sinks the daily run.
"""

from . import (
    amazon,
    apple,
    ashby,
    bloomberg,
    deshaw,
    eightfold,
    goldman,
    google,
    greenhouse,
    janestreet,
    jpmorgan,
    lever,
    meta,
    microsoft,
    millennium,
    spotify,
    tiktok,
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

BROWSER_FETCHERS = {
    "browser_goldman": goldman.fetch,
    "browser_jpmorgan": jpmorgan.fetch,
    "browser_millennium": millennium.fetch,
    "browser_tiktok": tiktok.fetch,
    "browser_janestreet": janestreet.fetch,
    "browser_deshaw": deshaw.fetch,
    "browser_meta": meta.fetch_browser,
    "browser_apple": apple.fetch_browser,
}
