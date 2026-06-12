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

Open questions for Alex after the next run:
- **Remote roles**: the best job of the day was remote-only. Flip
  `include_remote: true`, or keep them in near-miss?
- **Mid-level (II) roles**: Attentive SWE II scored 93.4. In or out?
- **Unleveled titles**: should `UNLEVELED_TITLE` near-misses with 5+-years
  descriptions be promoted to the main table (Stripe/OpenAI/Jane Street
  would enter)?

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
1. **ATS slug auto-discovery** (`python -m jobsearch discover <company>`):
   browser-load the careers_url, capture XHR to known ATS domains, emit the
   companies.yaml stanza. Unblocks Citadel, Warby Parker, Superhuman, Plaid —
   the slug-rot class keeps recurring, so tooling beats hand-research.
2. Goldman/JPMorgan XHR patterns — capture from a real session (funnel shows
   0 records despite pages loading).
3. Google/Apple/Bloomberg/Microsoft/Morgan Stanley browser fallbacks find no
   job records — same treatment.
4. Millennium browser capture is flaky (2 matches in run 2, 0 title-passes in
   run 3) — stabilize the XHR pattern / add retry.

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

### P4 — Application automation (prep only for now)
Staged: application packets → form prefill assist → approval queue →
(optionally, much later) unattended submit for allowlisted ATSes. Risks and
data model documented in
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

## Decisions needed from Alex

- **Remote-US roles** (`include_remote: false`): run 3's single best fit was
  remote-only. Flip it, or keep remote in near-miss?
- **Mid-level (II) roles**: Attentive SWE II scored 93.4 in near-miss. In or out?
- **Unleveled titles with 5+-years descriptions**: promote to main table?
  (Brings in Stripe, OpenAI, Jane Street, Meta.)
- Frontend/mobile hard-excluded, ML included — keep both choices?
