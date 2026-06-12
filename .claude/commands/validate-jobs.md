---
description: Web-verify today's top job matches and write verdicts to data/validation.json
---

Validate today's job-report results (docs/design-validation-loop.md).

1. Read `reports/validation-request.md`. It lists the top-ranked jobs and top
   near-misses, each with a `key`, a URL, and the claims to verify.

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
     resume at `data/resume.txt` (read it once at the start).
   - **flags**: anything off — reposted/evergreen listing, agency repost,
     level mismatch, location pool, salary far below NYC senior market.
   - For near-miss entries, also check whether the stated `filter_reason` is
     accurate (e.g. for UNLEVELED_TITLE, does the page reveal a level?), and
     note the answer in flags or fit_assessment.

3. Write `data/validation.json` exactly in the schema shown at the bottom of
   the request file, with `checked_at` set to the current UTC time and one
   verdict per key. Set `confidence` to your overall certainty (0-1) in the
   verdict.

4. Report back a short summary: how many verified / mismatched / stale, the
   most important flags, and whether any near-miss should be promoted into
   the main filter. Do not modify any other files.

The next `python -m jobsearch run` merges the verdicts into the report as a
Conf column and archives them to `data/validation-history/`.
