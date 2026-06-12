# Improvement Plan — v2 of the Daily Job Finder

Status: requirements captured 2026-06-12, based on the first two real runs
(2026-06-11: 54 matches / 15 companies / 20 board failures;
2026-06-12: 64 matches / 19 companies / 11 board failures).

This is the master document. Each workstream below links to a focused doc with
the full analysis and design. They are written so work can resume from these
docs alone if the session is lost.

## The questions this plan answers

1. **Why does Datadog dominate the fit ranking? Is K-means skewing results?**
   → Yes, three compounding structural causes found (none of them "Datadog is
   genuinely your best match"). See [analysis-scoring-skew.md](analysis-scoring-skew.md).
2. **45 companies showed zero senior-SWE matches. Are there really no jobs, or
   can we not fetch/see them?** → Breakdown: 11 fetch failures, 4 known
   no-API companies, ~30 "fetched fine, zero matched" — and at least 6 of
   those 30 are filter artifacts, not real zeros.
   See [analysis-zero-match-companies.md](analysis-zero-match-companies.md).
3. **If we broaden beyond the strict senior-SWE filter, do engineering-adjacent
   jobs fit the profile? Are they worth looking at?** → Needs a "near-miss"
   report section; designed in
   [analysis-zero-match-companies.md](analysis-zero-match-companies.md#near-miss-report).
4. **What's the confidence level in the matches? Should there be a validation
   step?** → Yes — a once-daily Claude-assisted validation loop that uses the
   Claude subscription (no API key, no per-token cost).
   See [design-validation-loop.md](design-validation-loop.md).
5. **How do we prep for automated application submission?** → Staged,
   human-in-the-loop design in
   [design-application-automation.md](design-application-automation.md).

## Workstreams, prioritized

### P0 — Scoring integrity (fixes the Datadog skew)
The fit scores currently drive every decision, and they have measurable bias.
- Score against the **full fetched corpus** (~7,200 postings), not the ~60
  post-filter survivors. Fixes unstable IDF and degenerate clusters.
- **Strip per-company boilerplate** before vectorizing (Datadog's shared
  marketing text inflates all its postings at once).
- **Persist a daily corpus snapshot** (`data/corpus/YYYY-MM-DD.jsonl.gz`) so
  scoring changes can be replayed/A-B tested offline.
- Details + experiments: [analysis-scoring-skew.md](analysis-scoring-skew.md).

### P1 — Visibility into the filter funnel (answers "why zero?")
- Per-company funnel counters logged and embedded in the report:
  `fetched → title_pass → location_pass → matched`.
- **Near-miss section** in the report: jobs that passed one gate but failed
  the other, scored and tagged with the reason
  (`SR_ABBREVIATION`, `UNLEVELED_TITLE`, `NO_NYC_LOCATION`, …).
- Fix the known title-filter gaps (e.g. Pinterest's "Sr.", Stripe's unleveled
  titles). Details: [analysis-zero-match-companies.md](analysis-zero-match-companies.md).

### P2 — Fetch reliability (the 11 still-failing boards)
Current failures and next actions are catalogued in
[analysis-zero-match-companies.md](analysis-zero-match-companies.md#fetch-failures).
Highlights: Goldman/JPMorgan XHR patterns need adjusting from a real captured
session; Google/Apple/Bloomberg browser fallbacks capture pages but find no
job records (selector/pattern fixes); Citadel/Warby Parker/Superhuman
Greenhouse tokens changed (need slug discovery from their careers pages);
Plaid's Lever board is empty (likely migrated).
- Build **ATS slug auto-discovery**: when a board 404s, browser-load the
  company's `careers_url`, capture XHR, and detect the real ATS + token
  automatically instead of hand-researching slugs.

### P3 — Validation loop (confidence scores)
Once-daily, subscription-funded (not API), human-triggered:
`python -m jobsearch validate-request` emits a compact file → you ask Claude
(Claude Code or claude.ai) to verify it via web search → Claude writes
`data/validation.json` → next run merges verdicts into the report as a
confidence column. Full design: [design-validation-loop.md](design-validation-loop.md).

### P4 — Application automation (prep only for now)
Staged: application packets → form prefill assist → approval queue →
(optionally, much later) unattended submit for allowlisted ATSes. Risks and
data model documented in
[design-application-automation.md](design-application-automation.md).

## Suggested order of implementation

| Step | What | Effort | Why first |
|------|------|--------|-----------|
| 1 | Corpus snapshot + full-corpus scoring + boilerplate strip | ~half day | Every other decision keys off fit scores |
| 2 | Funnel counters + near-miss report + title-filter fixes | ~half day | Recovers real jobs being dropped today (Pinterest, Stripe, …) |
| 3 | Validation request/response loop | ~half day | Adds confidence before any automation trusts the data |
| 4 | Slug auto-discovery + per-board XHR fixes | 1-2 days, incremental | Long tail of fetch reliability |
| 5 | Application packet generator (stage 1 of automation) | ~1 day | First concrete step toward auto-apply |

## Decisions needed from Alex

- Frontend/mobile roles are currently hard-excluded; ML roles are included.
  Keep both choices? (See title-filter notes in the zero-match doc.)
- Remote-US roles are excluded (`include_remote: false`). The near-miss
  section will show what that's hiding; revisit after one run.
- Max acceptable report size (currently top 100; near-miss adds ~20).
