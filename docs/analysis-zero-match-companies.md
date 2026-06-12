# Zero-Match Companies: What's Actually Happening

Question: *"For all the companies where there were no senior SWE jobs, what
are the reasons? Are there actually no jobs, or can you not fetch the jobs?
What's the breakdown?"*

## Breakdown for the 2026-06-12 run (45 zero-match companies)

| Bucket | Count | Companies |
|--------|-------|-----------|
| **A. Fetch failed** — we never saw their jobs | 11 | Google, Apple, Bloomberg, Microsoft, Morgan Stanley, Goldman Sachs, JPMorgan Chase, Citadel, Warby Parker, Superhuman, Plaid |
| **B. No scrapable board** (known, by design) | 4 | LinkedIn, Vimeo, Hinge, Two Sigma (listed under "check manually") |
| **C. Fetched fine, zero matched the filter** | ~30 | Stripe (498 fetched), OpenAI (732), Palantir (228), Roblox (229), Airbnb (223), Point72 (248), Brex (239), Oscar Health (235), Braze (196), Pinterest (174), Figma (169), Affirm (158), Notion (151), DRW (147), IMC (130), Justworks*, Uber (100), NVIDIA (100), Salesforce (100), Adobe (100), Coinbase (79), HRT (72), Jump (64), Dropbox (62), Peloton (60), Attentive (48), Betterment (27), Squarespace (24), Yext (24), Flatiron (23), Netflix (10), Meta/TikTok/Jane Street (browser-fetched) |

*(fetch counts from the 2026-06-11 run output; bucket C membership from the
6-12 report's zero-match list minus buckets A/B)*

**So: roughly 1/4 of the zeros are fetch problems, and among the rest there
are several false zeros caused by the filter — not by an absence of jobs.**

## Bucket C: the filter is eating real jobs

High-volume companies that fetched hundreds of postings and matched **zero**
are suspicious. Known/likely causes per company:

| Company | Fetched | Likely reason for zero | Real jobs lost? |
|---------|---------|------------------------|-----------------|
| Stripe | 498 | Stripe posts **unleveled titles** ("Backend Engineer, Payments" — no "Senior") | **Very likely** — they hire senior NYC backend constantly |
| Pinterest | 174 | Pinterest titles use **"Sr."** — the regex `\bsenior\b` never matches the abbreviation | **Very likely** |
| Palantir | 228 | Mostly unleveled ("Software Engineer, Product") | Likely |
| OpenAI | 732 | Mostly SF; many unleveled titles | Possible (few) |
| Uber | 100 | Fetcher pulls a 100-posting page — server-side query/location params may not be narrowing; NYC senior roles may be beyond page 1 | Likely (fetch-depth issue, not filter) |
| NVIDIA / Salesforce / Adobe | 100 each | Workday fetcher caps at ~100 and the **location facet isn't applied server-side** — first 100 global postings rarely include NYC | Likely (fetch-depth issue) |
| Netflix | 10 | Eightfold pagination returns only 10 | Likely (fetch-depth issue) |
| Airbnb / Roblox / Figma / Notion | 150–230 | Primarily SF/remote engineering orgs | Plausibly real zeros |
| Quant shops (Point72, DRW, IMC, HRT, Jump) | 60–250 | Titles like "Software Engineer" / "Quantitative Developer" without "Senior" | Mixed |

### Title-filter gaps to fix (concrete)

1. `Sr\.?` as an alternative to `senior` in every include pattern.
2. **Unleveled-title handling**: a new include tier — title matches
   `software engineer` (no level) **and** description matches
   `(\b[5-9]\+?|\bfive\b|\bsix\b).{0,20}years` → tag `UNLEVELED_TITLE`,
   include with a flag rather than dropping silently.
3. Consider `Lead Software Engineer` (currently only `lead (software|backend)`
   matches; "Lead Engineer, Payments" doesn't).
4. Decide explicitly: `frontend`/`mobile` stay excluded? ML stays included?
   (Today: yes/yes — Spotify's 8 matches are mostly ML roles.)

### Fetch-depth gaps to fix

- **Workday adapter**: pass the location facet in the POST body (Workday
  supports `locations`/`locationHierarchy` applied server-side) and paginate
  past 100 when the facet can't be applied.
- **Uber/Netflix/eightfold**: raise page size / iterate pages until the
  server-side query is exhausted (with the existing `max_per_company` cap).

## Near-miss report (answers "are adjacent jobs worth looking at?")

Question: *"For jobs that do exist that are in engineering or engineering
adjacent, when you broaden the search, do I fit the profile?"*

Design: instead of a boolean filter, classify every fetched job:

```
MATCH               title ✓ location ✓            → main table (today's behavior)
NEAR_TITLE          title ✗ location ✓ , title is engineering-ish
                    (engineer|developer|swe in title, failed seniority/track)
NEAR_LOCATION       title ✓ location ✗ , location is US-remote
OUT                 everything else               → dropped
```

- Near-miss jobs are **scored with the same model** and the top ~20 appear in
  a collapsed report section, each tagged with its reason
  (`SR_ABBREVIATION`, `UNLEVELED_TITLE`, `REMOTE_ONLY`, `MID_LEVEL`,
  `EXCLUDED_TRACK:frontend`, …).
- This answers the question *empirically every day*: if near-miss jobs
  consistently score above your main-table median, the filter is too tight in
  that direction; promote that reason code into the main filter. If they score
  low, the filter is right and you stop wondering.

### Funnel instrumentation

Per company, log and embed in the report:

```
Stripe: fetched=498  title_pass=0  loc_pass=132  matched=0  near_miss=41
```

One line kills all future guessing about "no jobs vs. can't see them."

## Bucket A: fetch failures — current diagnosis

| Board | Error (6-12 run) | Next action |
|-------|------------------|-------------|
| Google | v3 API 404; browser fallback found no records | Capture real XHR from google.com/about/careers/applications and update pattern |
| Apple | API 0 results; browser found no records | Same — capture real jobs.apple.com XHR shape |
| Bloomberg | API 403 (wrong URL hit); browser captured nothing | Fix API URL to careers.bloomberg.com/json/search/joblist; loosen XHR pattern |
| Microsoft | SSL hostname mismatch on gcsservices; browser fallback truncated error | Verify jobs.careers.microsoft.com XHR pattern from a real session |
| Morgan Stanley | Eightfold 403; browser fallback failed | Eightfold needs full browser context (cookies); raise wait time, capture pattern |
| Goldman Sachs | Browser ran, 0 records | XHR pattern `higher.gs.com/(api|graphql|search)` didn't hit; capture real pattern |
| JPMorgan | Browser ran, 0 records | Oracle Recruiting Cloud XHR pattern needs the real `requisitionList` path |
| Citadel | Greenhouse `citadel` 404 (also tried `citadelcorporate`) | Slug discovery (below) |
| Warby Parker | Greenhouse `warbyparker` 404 — but live postings exist on job-boards.greenhouse.io/warbyparker | Token likely changed; slug discovery |
| Superhuman | Greenhouse `grammarly` 404 | Rebrand likely changed token; slug discovery |
| Plaid | Lever org `plaid` returns 0 — but jobs.lever.co/plaid shows live jobs in web search | Possibly transient or UA-blocked; add UA header + retry, else slug discovery |

### Slug auto-discovery (proposed tool)

`python -m jobsearch discover <company>`: browser-loads the company's
`careers_url`, records every request to known ATS domains
(greenhouse, lever, ashby, workday, smartrecruiters, eightfold, phenom,
oracle), and prints the detected ATS + token + ready-to-paste companies.yaml
stanza. Run automatically (report suggestion) whenever a board 404s twice in a
row. This replaces manual web research per broken slug — the breakage class we
hit most.
