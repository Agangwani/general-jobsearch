# Design: resume-driven role targeting

## The bug this fixes

`config/settings.yaml` hard-coded the search to senior software engineering:
`search.query: senior software engineer`, and `title_include` / `title_exclude`
were SWE regexes. The resume only ever fed **scoring** (`score_jobs`
re-ranks postings that already passed the title filter). It had no path to
change *what* was searched or filtered.

So for a non-SWE resume the pipeline returned SWE jobs by construction. The
motivating case: a 20-year **Customer Success / consulting** resume (Gita
Gangwani) produced "129 NYC senior-SWE postings" — every Customer Success,
Program Manager, and consulting role was filtered out as a title miss, and the
SWE survivors were merely re-ranked. Proof, run through the old `JobFilter`:

| Title | Old verdict |
|---|---|
| Senior Customer Success Manager | out |
| Technical Program Manager | out |
| Senior Project Manager, Cloud | out |
| Senior Software Engineer, Backend | **match** |

## Approach: match the resume to an occupation, read off the targeting

The lever isn't a smarter model — it's a **knowledge base** that already encodes
"occupation → canonical titles → skills." We use an O*NET-shaped taxonomy
(`config/occupations.yaml`) and match the resume to its nearest occupation(s);
the matched entry *becomes* the search profile.

```
resume ─▶ match to nearest occupation(s)         (role_profile.match_occupations)
              │  TF-IDF cosine (default, no deps)
              │  MiniLM cosine  (optional, sentence-transformers)
              ▼
        RoleProfile: query · title_include · title_exclude · skills · categories
              │  (role_profile.build_profile)
              ├─▶ pipeline.run: replaces settings.search query + title filters
              └─▶ company_discovery: query + Muse categories
```

### Why O*NET

O*NET (US Dept. of Labor, public domain) ships ~900 occupations with an
Alternate Titles file (~56k real titles → occupation) plus per-occupation
skills and technology skills. That *is* the curated "keyword map" — maintained
professionally, no training required. We ship a hand-distilled **seed** of the
common role families in `config/occupations.yaml`; `tools/build_occupations.py`
regenerates the file from a full O*NET release to widen coverage. ESCO (EU) is
the analogous source for richer skills and was considered; O*NET's title
coverage made it the better fit for title-filter generation.

### Why two matchers

- **TF-IDF** (default): reuses the sklearn stack `scoring.py` already depends
  on — zero new dependencies, deterministic, runs in CI/offline. Each
  occupation's `document()` (name + titles + skills, titles/skills doubled) is
  embedded with the resume in a shared TF-IDF space and cosine-matched.
- **MiniLM** (`sentence-transformers/all-MiniLM-L6-v2`, ~80MB, optional):
  semantic matching that catches wording mismatches TF-IDF misses ("customer
  success" ≈ "client engagement"). `role_match_backend: auto` uses it when the
  package + model are available and **falls back to TF-IDF on any failure**
  (`_load_minilm` returns None), so installs without the extra never break.

This was the "TF-IDF + O*NET + MiniLM, most robust offline" combination
chosen during design.

### Generating the title filters

`build_title_filters` turns the matched occupations' titles into
`title_include` patterns by stripping level words ("Senior Data Engineer" →
`\bdata[\s/-]+engineer\b`), so a profile built from "Customer Success Manager"
still matches "Senior Customer Success Manager". Excludes are **seniority-aware**
(`infer_seniority` reads level cues + years of experience):

- senior / leadership → exclude junior/associate/entry-level titles;
- junior / mid IC → exclude manager/director/VP (an IC doesn't want management
  roles);
- a **management occupation** (`manage: true`, e.g. Engineering Manager,
  Management Consultant) never excludes manager/director.

This is what lets Gita's leadership-level Customer Success profile keep
"Customer Success **Director**" while a junior SWE profile drops management
titles. On her resume the engine now resolves **Customer Success Manager +
Management Consultant** (leadership), query "customer success" — and a Senior
Software Engineer posting drops from `match` to a broadened-search near-miss.

### Blending

A resume often straddles roles. `build_profile` blends a close runner-up
(score ≥ `blend_ratio` × top, default 0.85, up to 2 occupations) so the
profile spans, e.g., Customer Success *and* Management Consultant rather than
forcing one.

## Integration & safety

- **Default on, reversible.** `search.role_targeting: auto` is the shipped
  default. `manual` uses the hand-tuned `settings.yaml` regexes verbatim
  (preserving the curated SWE filters for users who want them).
- **Confidence gate.** If the best match scores below
  `search.role_match_min_score` (default 0.02 — guards a garbled/empty resume),
  targeting is skipped and the manual filters are used. `resolve_profile`
  centralizes this so `run` and `discover-companies` behave identically.
- **Locations untouched.** `apply_profile` substitutes only query + title
  filters; `search.locations`, remote, and pay knobs are the profile's job to
  leave alone — *what role* vs. *where*.
- **Visibility.** The run logs the derived profile and writes
  `data/role_profile.json`; the `/resume` page shows the detected target roles
  and relevant skills with a **▶ Run pipeline** button that triggers a run in
  the background.

## Tests

`tests/test_role_profile.py` (offline, TF-IDF backend; MiniLM exercised only
when installed): the CS resume matches a customer-facing/consulting role and
*not* Software Engineer; a SWE resume still matches Software Engineer;
seniority inference; seniority-aware exclude generation; and the end-to-end
inversion of the reported bug (CS titles match, SWE title no longer a main-table
match). `tests/test_webapp.py` covers the resume-page role panel and the run
trigger.

## Future work

- Distil and ship a broader slice of O*NET (the seed covers ~25 families).
- LLM refiner (Claude Haiku) as an optional third backend for resumes that
  match no occupation cleanly.
- Surface `data/role_profile.json` in the daily report header.
- Feed the profile's skills into scoring as an additional signal.
