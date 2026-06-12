---
name: validate-jobs
description: Web-verify the day's top job-report matches and near-misses against the live posting pages, then write per-job verdicts to data/validation.json. Use after a `python -m jobsearch run` when reports/validation-request.md exists, or whenever the user asks to validate, verify, or fact-check the job report.
---

# Validate today's job-report results

Validate the jobsearch pipeline's daily output (design:
docs/design-validation-loop.md in the jobsearch repo).

## Inputs

- `reports/validation-request.md` — lists the top-ranked jobs and top
  near-misses, each with a `key`, a URL, and the claims to verify. If the
  file is not available in the working directory, ask the user to paste its
  contents.
- `data/resume.txt` — read once at the start; used for fit assessment. If
  unavailable, ask the user for a resume summary.

## Steps

1. Read `reports/validation-request.md`.

2. For each posting, verify via web search and/or fetching the posting URL:
   - **live**: the posting page loads and is not marked closed / "no longer
     accepting applications". A 404 or redirect to a generic careers page
     means not live.
   - **senior_confirmed**: the page shows the role is senior-level (title,
     level, or a 5+ years experience requirement).
   - **nyc_confirmed**: the role is NYC-based or NYC-hybrid. A multi-state or
     nationwide-remote pool that merely *includes* New York is NOT confirmed —
     flag it instead.
   - **fit_assessment**: one line on whether the role genuinely matches the
     resume.
   - **flags**: anything off — reposted/evergreen listing, agency repost,
     level mismatch, location pool, salary far below NYC senior market.
   - For near-miss entries, also check whether the stated `filter_reason` is
     accurate (e.g. for UNLEVELED_TITLE, does the page reveal a level?), and
     note the answer in flags or fit_assessment.

3. Write `data/validation.json` exactly in the schema shown at the bottom of
   the request file, with `checked_at` set to the current UTC time and one
   verdict per key. Set `confidence` to your overall certainty (0-1) in the
   verdict. If there is no filesystem access, output the JSON in a code
   block for the user to save as `data/validation.json`.

4. Report back a short summary: how many verified / mismatched / stale, the
   most important flags, and whether any near-miss should be promoted into
   the main filter. Do not modify any other files.

The next `python -m jobsearch run` merges the verdicts into the report as a
Conf column and archives them to `data/validation-history/`.
