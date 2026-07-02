# Design: the startup pipeline

`python -m jobsearch discover-startups` + `run-startups`

## Problem

The main pipeline targets a curated registry of large employers (FAANG + the
NYC top 50). A startup search is a different question with a different company
universe: *which **startups** in a given city are hiring someone like me?* — and
when you weigh a startup you care about facts the main pipeline never tracks:
how many people work there, how much they've raised and from whom, who's on the
team. The ask was a **separate, second pipeline** that searches all startups in
a city, scores them with the same fit map, and tracks those startup-specific
facts — with the tracker able to show only startups, hide startups, or mix both.

## Shape

It is the *same machinery* as the main pipeline (fetch boards → filter → TF-IDF
+ K-means fit → report → fit map), pointed at a startup universe and writing to
its own files. Rather than fork `pipeline.run` / `company_discovery`, both are
parameterized by a small **`Track`** record (`jobsearch/tracks.py`):

| | main track | startups track |
|---|---|---|
| registry | `config/companies.yaml` + `data/companies.discovered.yaml` | `config/startups.yaml` (optional) + `data/companies.startups.yaml` |
| reports | `reports/` | `reports/startups/` |
| fit map | `reports/clustering.json` | `reports/startups/clustering.json` |
| seen-state | `data/seen_jobs.tsv` | `data/seen_jobs.startups.tsv` |
| corpus | `data/corpus/` | `data/corpus-startups/` |
| metadata | — | `data/startup_meta.json` |
| location | `search.locations` | `startups.locations` (defaults to the main city) |

Role targeting, ranking knobs, and the scorer are **shared**, so a startup run
scores exactly the way the main run does and the Fit map "just works" for it.

```
resume ─▶ discover-startups ─▶ YC directory + HN + The Muse ─▶ CompanyLead[]+meta
                                     │
            rank by resume fit · resolve each to its ATS board (discover.py)
                                     ▼
   data/companies.startups.yaml   +   data/startup_meta.json
                                     │
              run-startups (fetch → filter → fit → report → fit map)
                                     ▼
   reports/startups/*  ──ingest──▶  tracker DB (jobs.is_startup=1 + startup_companies)
                                     ▼
        dashboard toggle: all · 🚀 only startups · 🏢 hide startups
```

## The startup universe — "all startup companies"

The new lead source is **Y Combinator's company directory**
(`jobsearch/sources/ycombinator.py`), read from the community OSS JSON mirror
(`yc-oss.github.io/api`, a static mirror of YC's public directory). It is
keyless and documented — the same ToS bar as The Muse and the HN source, and
exactly the "YC company directory" listed as future work in
`design-company-discovery.md`. It is the canonical, near-complete list of
startups, filterable by city and status, and each company resolves to its own
ATS board through the existing `discover.py` probe. HN "Who is hiring?" and The
Muse stay in the source list because they surface startups posting *right now*;
the three merge and dedupe like any other discovery run.

Why not Wellfound/AngelList/Built In? Same reason as the main pipeline: they sit
behind bot protection with no public API, and scraping them would violate ToS.

## Startup metadata (the "helpful info")

`jobsearch/startups.py` defines `StartupMeta` — employees, founded, batch,
stage, last round + amount, total raised, investors, notable people, industry,
status, links — and how it's populated, honestly, from free sources:

- **Structured** fields come straight from YC: `team_size` → employees, plus
  batch, status, stage, industry, founded year, website. Every YC company is
  YC-backed, so the investor list is seeded with "Y Combinator".
- **Funding signals** that no free *structured* API exposes (round size, lead
  investors, notable hires) are mined heuristically from the free text we
  already have — HN blurbs and YC descriptions routinely say "Series A, $20M,
  backed by a16z". `extract_funding` / `extract_people` / `find_investors` do
  this with conservative regexes and a curated investor list.

Everything else is left blank and is **user-editable** in the UI. The honest
position, stated in the UI and here: precise, current cap-table and
leadership data needs a paid source (Crunchbase/PitchBook) or manual entry. The
schema holds it either way, and a `user_edited` guard means a later ingest never
clobbers what you typed.

`discover-startups` writes the metadata to `data/startup_meta.json` (company →
meta, keyed by normalized name); `ingest` loads it into the `startup_companies`
table.

## Tracker integration

One tracker, both kinds of job. The integration is deliberately thin:

- `jobs.is_startup` (one column, added by an additive migration) marks a job
  whose company is a known startup. It's set by `refresh_startup_flags` on every
  ingest by matching `jobs.company` (normalized) against `startup_companies` — so
  a startup is flagged even if the *main* run is what surfaced it.
- `ingest` now pulls **both** tracks' `latest.json` (each from its own corpus),
  loads the metadata sidecar, then refreshes flags.
- The dashboard gets a three-way **startup scope** toggle (`startup_scope` =
  `all` / `only` / `hide`) wired into `search_jobs`, and the headline counters
  split startup vs. established (`stack_counts` returns `startup`/`other`
  sub-totals). Startup rows show a 🚀 badge with employees/stage inline.
- `/startups` is a directory of tracked startups with their facts and open-role
  counts; `/startups/{key}` shows + edits one. `/clusters?track=startups` is the
  startup fit map. The Startups page (and `/run?track=startups`) can launch the
  startup pipeline from the browser.

## Failure modes (same philosophy as the rest of the tool)

- A dead source never sinks discovery — each is wrapped (`SourceSkip` for
  environment gaps like a missing Adzuna key, any other exception logged).
- An empty startup registry is fine: `run-startups` writes an empty report
  rather than erroring, and the UI shows a "run discover-startups" empty state.
- Probe-resolved slugs can collide on common startup names — entries record
  `discovered_via: "… (probe)"`; `verify --startups` and the report funnel make
  a wrong board visible, exactly as in the main pipeline.

## Configuration

Everything lives under `startups:` in `config/settings.yaml`: the city
(`location` / `locations`), `sources`, `max_companies`, the YC slice/status
filters, and the per-track output paths. Defaults target New York and the YC
`hiring` slice. All generated artifacts are gitignored (they derive from your
resume), like the main pipeline's.

## Future work

- A `--track startups` flag on `verify` is wired (`verify --startups`); a daily
  GitHub Action for the startup pipeline ships disabled (manual dispatch) so it
  never surprises a repo with commits.
- Optional paid enrichment (Crunchbase key) to fill funding/leadership exactly,
  using the same `StartupMeta` shape and `user_edited` guard.
- A startup-vs-established comparison view layered on the existing fit map.
