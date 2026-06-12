# Application Automation: Staged Roadmap

Goal: *"Prep for a stage where we automate actual application submission to
these jobs."*

Guiding principle: **automate the preparation completely, automate the
submission carefully.** A bad fetch costs nothing; a bad submission burns a
real opportunity at a company that's always on the list (these are the FAANG +
top-50 NYC employers — you only get to make a first impression once per
company per cycle). Human review stays in the loop until the packet quality is
proven, and some ATSes additionally prohibit or CAPTCHA-block unattended
submission.

## Stage 0 — prerequisites (build first)

1. **Validated shortlist** — automation only draws from jobs with
   confidence ≥ 0.7 (see design-validation-loop.md). Never auto-apply to an
   unvalidated posting.
2. **Profile store** — `data/profile.yaml` (gitignored; contains PII):
   contact info, work authorization, links (GitHub/LinkedIn/portfolio),
   salary expectation ranges, notice period, EEO self-identification answers
   (each marked `answer` or `decline`), and references to resume variants.
3. **Answer bank** — `data/answers.yaml`: canonical answers to recurring
   screening questions ("Why this company?", "years of experience with X",
   visa sponsorship, hybrid/onsite willingness), keyed by question pattern.
   Grows over time; every new question encountered gets logged for review.
4. **Application ledger** — `data/applications.jsonl`: one record per
   application ever made (job key, company, date, resume variant, packet
   path, status, response). Prevents double-applying (many ATSes flag
   duplicate applicants), powers response-rate analytics per company/variant,
   and enforces a per-company cooldown.

## Stage 1 — application packets (no submission)

`python -m jobsearch packet <job-key>` generates
`applications/<company>/<job-id>/`:

- `posting.md` — frozen copy of the posting (title, description, URL, date)
  so the packet survives the posting being taken down.
- `resume-notes.md` — which resume bullets to emphasize for this role;
  keyword gaps between resume and posting (from the existing TF-IDF space —
  the highest-weight posting terms absent from the resume).
- `cover-letter.md` — draft, generated in Claude Code on demand
  (subscription, not API — same pattern as the validation loop).
- `questions.md` — screening questions scraped from the apply form (where
  fetchable) with proposed answers from the answer bank, gaps highlighted.

Human applies manually with everything pre-staged. **This alone is most of
the time savings of full automation, at zero risk.** Instrument the ledger
from day one to measure response rates.

## Stage 2 — form prefill assist (human submits)

Playwright (already a dependency) opens the apply page **headed**, fills
fields from `profile.yaml` + answer bank + packet, uploads the resume
variant, then **stops and waits**. Human reviews every field, completes
anything unknown (new questions get appended to the answer bank), solves any
CAPTCHA, and clicks submit.

- Start with the two form families covering most of the list: Greenhouse and
  Lever (standardized DOM). Ashby next. Workday is its own project (multi-page
  account-based flows) — keep it packet-only until Stage 2 is proven.
- Every run saves a pre-submit screenshot + field dump into the packet dir
  (audit trail).

## Stage 3 — approval-queue submission (one click per application)

When Stage-2 accuracy has been verified across ~20+ real applications:

- Nightly: generate packets + prefilled forms for the day's shortlist; queue
  them in `applications/queue.md` with screenshots.
- You review the queue (morning coffee) and approve/reject each; approved ones
  are submitted by the same Playwright session, results logged to the ledger.
- Still no fully unattended writes: approval is the human gate; submission is
  mechanical.

## Stage 4 (optional, far later) — unattended submission

Only if Stage 3 shows ~100% field accuracy and zero duplicate/error incidents,
and **only** for allowlisted ATSes with simple forms (Greenhouse/Lever),
standard questions fully covered by the answer bank, no CAPTCHA, and a daily
cap (e.g. ≤5). Anything novel (unseen question, layout change, CAPTCHA,
attachment request) aborts to the Stage-3 queue. Hard rules regardless of
stage:

- Never fabricate an answer; unknown → human queue.
- Never bypass CAPTCHAs or bot checks — that's the site telling us not to
  automate; respect it (and per-site ToS) or keep that site human-submitted.
- Per-company cooldown (e.g. 1 application/company/2 weeks) and a global
  daily cap.
- Everything submitted is reproducible from its packet dir.

## Sequencing relative to other workstreams

```
scoring fixes (P0) ─┐
filter funnel (P1) ─┼─→ validated shortlist (P3) ─→ Stage 1 packets ─→ Stage 2 prefill ─→ Stage 3 queue
fetch repairs (P2) ─┘
```

Packets (Stage 1) can start as soon as the validation loop exists — they
don't require any submission machinery and immediately compound the value of
the daily report.
