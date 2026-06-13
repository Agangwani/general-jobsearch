# Design: dynamic company discovery

`python -m jobsearch discover-companies`

## Problem

`config/companies.yaml` was hand-built from one specific resume (senior
backend SWE, NYC). The repo is meant to generalize to any resume, and the
company set is the one piece that doesn't: the right employers for a data
scientist, a designer, or a product manager overlap only partially with the
right employers for a backend engineer. A static registry also rots — it
misses every company that started hiring after the list was written.

The fix inverts the data flow. Instead of *registry → jobs*, discovery goes
*generalized boards → companies → their own boards*:

```
resume ──▶ query/categories ──▶ SOURCES (aggregator boards) ──▶ CompanyLead[]
                                       │ The Muse · HN hiring · Adzuna
                                       ▼
        merge by normalized name · drop known/excluded · rank by resume fit
                                       ▼
        resolve each lead to its OWN ATS board   (discover.py: URL classify,
                                       │          then slug probe)
                                       ▼
        data/companies.discovered.yaml  ──merged-under──▶ config/companies.yaml
                                       ▼
        the normal daily run (fetch → filter → rank → report), unchanged
```

The principle from the README still holds end-to-end: aggregators are used
only to learn **who** is hiring; jobs themselves are always fetched from and
linked to the **company's own** board.

## Strategies surveyed for finding NYC companies

| Strategy | Status | Why |
|---|---|---|
| **The Muse public API** | ✅ `sources/themuse.py` | Documented, free, keyless; location + category filters; NYC-heavy inventory with employer names and descriptions. |
| **HN "Who is hiring?" via Algolia API** | ✅ `sources/hn_hiring.py` | Keyless, monthly, the densest startup signal; comments often link the company's ATS board directly, which makes resolution free and reliable. |
| **Adzuna search API** | ✅ `sources/adzuna.py` (opt-in) | Broadest employer coverage (enterprises that never post on HN); free API key required, so it skips cleanly when `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are unset. |
| Built In NYC directory | ◻ future | The canonical NYC tech-company directory, but no public API — needs a browser-survey source (Playwright, like the browser fetchers). |
| YC company directory | ◻ future | Public site backed by an Algolia index, filterable by region/industry; quasi-public credentials make it fragile. |
| Wellfound (AngelList), Otta, levels.fyi | ✗ | Bot-protected / no public API; scraping would violate ToS — same policy as LinkedIn in `manual_check`. |
| LinkedIn / Indeed / Google Jobs | ✗ | No usable public APIs; aggressive bot defense; explicitly out of scope already. |
| Tech:NYC member list, "awesome NYC startups" repos | ◻ manual | Good one-time seed material for companies.yaml, not worth automating. |

Adding a source = one module in `jobsearch/sources/` with
`fetch(session, ctx) -> list[CompanyLead]` plus a registry line in
`sources/__init__.py`. Parsing must be a pure function over the payload so
it's offline-testable (network is unavailable in the dev sandbox and in CI).

## How each stage works

**Personalization.** Three resume-derived inputs make discovery user-specific:
the Muse *categories* are inferred from `resume.extract_keywords` + the
configured `search.query` (`infer_categories`, override via
`discovery.categories`); the Adzuna `what` term is `search.query`; and final
lead ranking is TF-IDF cosine between the resume and each lead's evidence
(titles + description snippets, the lead's own name stripped — same defense
as `scoring._company_name_re`), times a small log-scale bonus for companies
seen posting several matching roles. Location comes from
`discovery.location` (sent to the APIs) plus the existing `search.locations`
substrings (client-side check), so retargeting the whole tool to Austin is
two settings.

**Identity.** Sources spell employers differently ("Ramp" vs "Ramp, Inc."),
so leads merge on `utils.normalize_company_name` (lowercase tokens, legal
suffixes and a leading "the" dropped). The same key dedupes against the
curated registry and enforces `discovery.exclude_companies`.

**Resolution** reuses `discover.py`: first `survey_urls` over any URLs found
in the lead's own evidence (an HN comment linking
`jobs.ashbyhq.com/ramp` is the company self-reporting its board — resolved
as `(url)`), else `probe_slugs` hits the public Greenhouse/Lever/Ashby/
SmartRecruiters APIs with name-derived slugs — resolved as `(probe)`.
Unresolved leads are not dropped: they become `manual_check` entries so the
daily report keeps surfacing them.

**Output** is a generated file, not an edit to companies.yaml:
`data/companies.discovered.yaml` (gitignored — it's derived from your
resume). `config.load_registry` merges it under the curated file on every
`run`/`verify`. Precedence rules:

- curated `companies.yaml` always wins name conflicts;
- `discovery.exclude_companies` is enforced at *load* time too, so a stale
  generated file can never re-add your current employer;
- regenerating overwrites the file — to pin or hand-fix an entry, move it
  into `companies.yaml` (the generated header says exactly this).

## Known risks and their mitigations

- **Slug collisions on probe.** A lead named "Mercury" can probe-match a
  different Mercury's Greenhouse board. Every entry records
  `discovered_via: "<sources> (url|probe)"`; `(probe)` entries are the ones
  to spot-check. `verify` catches dead boards, and the report's per-company
  funnel makes a board that contributes zero location-matching jobs visible.
- **Aggregator drift.** Each source is wrapped per-source (`SourceSkip` for
  environment gaps, everything else logged as a source error), mirroring how
  one broken company board never sinks the daily run.
- **Noise volume.** `discovery.max_companies` caps additions per run, and
  relevance ranking decides *which* leads get those slots; everything else
  simply isn't resolved.

## Future work

- Browser-survey source for Built In NYC (and the YC directory).
- Optional auto-refresh: re-run discovery from `run` when the generated file
  is older than N days.
- Post-resolution sanity check: fetch a page of the resolved board and
  require ≥1 location-matching posting before admitting the entry.
- UI surface: a "discover companies" button next to the resume upload.
