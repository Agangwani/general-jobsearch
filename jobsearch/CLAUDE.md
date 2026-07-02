# jobsearch/ — pipeline rules

CLI in `__main__.py`; orchestration in `pipeline.py` (fetch → filter → score → report).

## Conventions
- **Graceful degradation is mandatory.** A single failing board or fetcher must never abort a
  run — keep the broad per-board `# noqa: BLE001` catches. API fetchers (`FETCHERS`) must work
  without Chromium; browser fetchers (`BROWSER_FETCHERS`, `browser.py`) are optional.
- **Two isolated pipelines.** Main and startups keep separate report dirs, seen-state
  (`seen_jobs.tsv`), and corpus dirs — never let a change make them share state or files.
- **Config over hardcoding.** Tunables (queries, title include/exclude regexes, locations,
  ranking half-life/clusters/caps, fetch timeouts) live in `config/settings.yaml` with code
  defaults. Company registry is `config/companies.yaml`; role knowledge is
  `config/occupations.yaml`. Add a new company/ATS there, not inline.
- **Resume-driven & non-repetitive.** Scoring keys off `data/resume.txt`; generated registries
  (`companies.discovered.yaml`, `companies.startups.yaml`) and startup metadata are gitignored —
  don't commit them, and don't make output repeat the same jobs across runs.
- Adding a fetcher: register it in `fetchers/` (API vs browser) and confirm
  `python -m jobsearch verify` still reports it reachable.

Tests for this package live in `tests/` (`test_scoring.py`, `test_filters.py`,
`test_sources.py`, `test_discover.py`, `test_end_to_end.py`, industry-resume fixtures, …).
