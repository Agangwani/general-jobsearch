# Improvement Plan — v2 of the Daily Job Finder

Status: requirements captured 2026-06-12 (runs 1–2); **P0 and P1 shipped and
validated against run 3** (2026-06-12 14:50 UTC, the first run on the new
code: 65 matches / 18 companies / funnel + near-miss live).

## Run-3 scoreboard (what the fixes did)

| Check | Result |
|-------|--------|
| Datadog skew | Fit 88.5 → 63.1, rank #2 → #7; its genuinely-matching roles stayed in the top table ✅ |
| "Sr." recall | Pinterest title passes 0 → 31 ✅ |
| Funnel answers "why zero" | Every zero-match company now explained by one table row ✅ |
| Near-miss value | Day's best fit (100.0) was a near-miss — Coinbase Senior SWE Data Platform, hidden by `REMOTE_ONLY`; OpenAI has 41 near-misses, Palantir 36, Jane Street 32 ✅ |
| Defects found in run 3 | (a) corrupted-merge of seen_jobs.json silently flagged all 65 jobs 🆕 — state now TSV + salvage parser; (b) funnel counted pre-age-cutoff — now age-aware with an `Aged out` column; (c) cluster topics exposed company-name tokens + `nbsp` entity leakage — both stripped |
| Fetch gaps confirmed | Workday tenants returned 0 NYC rows (NVIDIA 98 title-passes / 0 loc) — location term + deeper paging shipped; Amazon page-1 had only 9 NYC rows — pagination to 300 shipped; D. E. Shaw card-text titles cleaned |

~~Open questions for Alex after the next run~~ — answered 2026-06-12, see
"Decisions from Alex" at the bottom: remote roles enter only with a posted
pay range ≥ $200k, unleveled titles are promoted, mid-level stays near-miss.

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

### P0 — Scoring integrity ✅ SHIPPED (PR #3 + run-3 follow-ups)
Full-corpus scoring, boilerplate stripping, corpus snapshots, cluster topics,
skew warning — plus run-3 follow-ups: company-name token stripping,
compensation/EEO stoplist, HTML-entity fix.
Remaining: rerun the A/B experiments on corpus snapshots once a few days
accumulate. Details: [analysis-scoring-skew.md](analysis-scoring-skew.md).

### P1 — Filter funnel + near-miss ✅ SHIPPED (PR #3 + run-3 follow-ups)
Funnel table (now age-aware), near-miss section with reason codes, "Sr." fix,
expanded REMOTE_HINTS, merge-resilient seen-state.
Remaining: the three filter-policy questions for Alex above (remote,
mid-level, unleveled promotion).
Details: [analysis-zero-match-companies.md](analysis-zero-match-companies.md).

### P2 — Fetch reliability (re-prioritized by funnel evidence)
Quick wins shipped with the run-3 follow-ups: Workday location term + deeper
paging (NVIDIA/Adobe/Salesforce/Etsy), Amazon pagination, D. E. Shaw title
cleanup. Still open, in priority order:
1. ~~**ATS slug auto-discovery**~~ ✅ SHIPPED — `python -m jobsearch
   discover "<company>" [--url careers-page]`: probes name-derived slugs
   against the Greenhouse/Lever/Ashby/SmartRecruiters public APIs first (no
   browser needed), then falls back to a headless-Chromium survey of the
   careers page that classifies every URL the frontend touches (XHRs,
   iframe embeds, redirects — Workday tenant/site pairs included) and emits
   a ready-to-paste companies.yaml stanza. Run it for Citadel, Warby
   Parker, Superhuman, Plaid.
2. ~~Goldman/JPMorgan XHR patterns~~ ✅ SHIPPED (pending real-run
   validation) — `BrowserRuntime.harvest()` now also collects every JSON
   response regardless of URL pattern *and* JSON embedded in the final DOM:
   SPA state globals, **Phenom's `window.phApp.ddo`** (careers.jpmorgan.com
   and mlp.com embed page-1 results there — no XHR needs to fire), and
   schema.org JobPosting JSON-LD. Each browser fetcher parses precisely
   first, then falls back to the generic extractor
   (`fetchers/_generic.py`) over everything harvested.
3. ~~Google/Apple/Bloomberg/Microsoft/Morgan Stanley browser fallbacks~~
   ✅ same treatment — plus cookie-consent auto-dismissal and scroll
   passes, both of which commonly block job XHRs on these sites.
4. ~~Millennium flaky capture~~ ✅ — `harvest()` retries once with a doubled
   settle window when nothing job-shaped came back, and the Phenom embedded
   state works even when the jobs XHR never fires.

The next scheduled Actions run is the integration test for 2–4; per-site
residue (if any) shows in the funnel / needs-attention sections.

### P3 — Validation loop (confidence scores) — NOW THE TOP PRIORITY
Once-daily, subscription-funded (not API), human-triggered:
`python -m jobsearch validate-request` emits a compact file → you ask Claude
(Claude Code or claude.ai) to verify it via web search → Claude writes
`data/validation.json` → next run merges verdicts into the report as a
confidence column. Full design: [design-validation-loop.md](design-validation-loop.md).

Promoted above the remaining P2 work after run 3, for two reasons:
- It's the only path to **labeled precision** — the one metric that can say
  whether the fit scores themselves are good (see the metrics framework in
  the validation doc). Scoring changes without it are unfalsifiable.
- Validation requests now include top near-misses, which doubles as the
  decision input for the three filter-policy questions above.

### P3.5 — Application-tracking UI ✅ SHIPPED (see [design-frontend.md](design-frontend.md))
Local FastAPI + SQLite app (`python -m jobsearch ui`): two stacks
(to-apply/applied), searchable job DB with exact insertion timestamps and
append-only history, integrated Playwright apply-browser with submission
detection, copy-paste profile panel, resume viewer, search-config viewer.
**Gmail connect is now fully implemented** (raw OAuth loopback flow + REST
sync, zero new dependencies): drop a Google OAuth Desktop-app client JSON at
`data/credentials.json`, click Connect on /emails, then "⟳ Sync now" pulls
recent inbox mail, stores only job-relevant messages, links them to
applications, and auto-advances applied → confirmed on confirmations.

### P4 — Application automation — Stage 2 (auto-fill) ✅ SHIPPED
**Auto-fill apply is live** ([design-autofill.md](design-autofill.md)): every
"⚡ Auto-fill apply" click (job page or per-row in the table) opens its own
tab in the shared integrated browser, fills the form from the profile
(formatted values, parallel field matching, EEO/cover-letter questions
deliberately skipped and reported), and leaves submit to the user.
Remaining stages: per-ATS field maps learned from user corrections, approval
queue, and (much later, opt-in) unattended submit — risks and data model in
[design-application-automation.md](design-application-automation.md).

## Suggested order of implementation (updated after run 3)

| Step | What | Status |
|------|------|--------|
| 1 | Corpus snapshot + full-corpus scoring + boilerplate strip | ✅ shipped, validated run 3 |
| 2 | Funnel counters + near-miss report + title-filter fixes | ✅ shipped, validated run 3 |
| 2.5 | Run-3 follow-ups: state TSV, age-aware funnel, company-token strip, Workday/Amazon/DEShaw fetch fixes | ✅ shipped |
| 3 | Validation request/response loop (+ `/validate-jobs` command) | ✅ shipped — run `/validate-jobs` daily in Claude Code; verdicts appear as a Conf column next run |
| 4 | Slug auto-discovery, then per-board XHR fixes | ⏭ next |
| 5 | Application packet generator (stage 1 of automation) | after a few days of validation labels |

## Decisions from Alex (2026-06-12) — all implemented

- **Remote-US roles**: include in the main table **only when the posting
  shows a pay range topping out at/above $200k/yr**
  (`search.remote_min_pay: 200000`). Remote roles without a posted range or
  below the floor stay in near-miss as `REMOTE_NO_PAY_RANGE` /
  `REMOTE_PAY_BELOW_MIN`.
- **Unleveled titles with 5+-years descriptions**: **promoted** to the main
  table when the title looks like a software role
  (`search.promote_unleveled: true`) — brings in Stripe, OpenAI, Jane Street.
- **Frontend/mobile hard-excluded, ML included**: confirmed, kept as-is.
- **Mid-level (II) roles**: stay in near-miss (not promoted).
