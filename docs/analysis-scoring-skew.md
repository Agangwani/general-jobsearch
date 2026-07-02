# Why Datadog Dominates: Scoring-Skew Analysis

> **Update (2026-07-02) — second skew pass, on the 8038-posting corpus.** A
> deeper audit of the fit map found the cluster term was still injecting skew,
> for two newly-identified reasons, plus a data-completeness issue. Fixes
> shipped this pass:
>
> - **Location leaked into the vectors.** `_doc` fed `job.location` into the
>   TF-IDF document, so K-means carved out a "new york, york, locations" cluster
>   that bucketed strong SWE matches *by city*. Google NYC roles dropped 60–67
>   ranks into it. Location is already a hard filter, so it carries no fit signal
>   among survivors — it is now excluded from the vectorized document.
> - **The cluster term was over-weighted for how weak the clusters are.**
>   Silhouette is < 0.08 at *every* k (2…40): the postings don't cluster cleanly
>   into skill groups, and several clusters collapse to a *single company*
>   (c16 = Asana 146/146, c13 = Lyft, c3 = Jane Street, c1 = Brex) — i.e. they
>   recover company authorship, not skill. Their affinity reflects the company's
>   average posting, so a genuinely strong Asana AI-SWE role was demoted ~48
>   ranks into Asana's own low-affinity cluster. `cluster_weight` lowered
>   0.15 → 0.05, which cuts the cluster-driven fit swing from ~17 pts to ~6 and
>   the worst demotion from 67 ranks to ~30, while keeping the /clusters map
>   meaningful. (The rank-stability metrics are partly circular — they are
>   defined as deviation from pure cosine — so the weight was chosen on the
>   *mechanism*: cluster affinity ≈ company authorship, which should not weigh
>   heavily, not on a self-referential "improvement" number.)
> - **Jane Street postings carried raw HTML** (fetcher never called
>   `strip_html`) → an `li/h3/em/nbsp` markup cluster. Fixed in the fetcher, with
>   a `strip_html` safety-net added at the vectorization boundary (`_doc`).
> - **Deferred, not yet fixed — empty descriptions.** 259/8038 postings (whole
>   companies: Salesforce 85/85, NVIDIA, Google, Apple, Netflix, Microsoft,
>   Millennium — all 100%) arrive with *empty* descriptions because those
>   fetchers fall back to link-scraping without the body. Those roles are scored
>   on title alone and are systematically *deflated*. This is a fetcher
>   data-completeness bug, not a scoring bug; excluding them is the wrong fix
>   (it would hide real, high-cosine roles), so it is left for a fetcher pass —
>   treat title-only postings as low-confidence.
> - **Considered and rejected — dropping numeric tokens.** Numbers in the resume
>   (achievement metrics like "27%", "36%") do leak a little cosine weight, but
>   the effect is ~0.7% of similarity on average and `max_features=30000` is
>   saturated, so filtering them just admits replacement bigrams. Net-neutral;
>   not shipped.

> **Status (2026-06-12, after run 3):** fixes shipped and validated. Datadog
> company fit dropped 88.5 → 63.1 (rank #2 → #7) while its genuinely strong
> roles (eBPF, Code Gen, Infrastructure R&D) stayed in the top table — exactly
> the predicted shape: position earned by role text, not marketing text.
> Residual issues found in run 3 and fixed the same day:
>
> - Cluster topics exposed leftover company-authorship clustering ("datadog,
>   benefits growth, nbsp datadog", "mongodb, mongodb base", "justworks,
>   mercury, diversity, salary ranges"). Three causes, three fixes: each
>   company's own name tokens are now stripped from its postings before
>   vectorizing; a compensation/EEO stoplist (benefits, salary, diversity,
>   stock, …) was added; and `strip_html` now unescapes double-encoded
>   entities (`&amp;nbsp;` was leaking literal "nbsp" tokens).
> - Scale-to-100 now spans matched ∪ near-miss jobs; on 6-12 the single best
>   fit of the day (100.0) was a near-miss (Coinbase remote). This is honest
>   but means main-table fits can look deflated vs. earlier reports — fit
>   values are comparable within a run, not across code changes.

Question: *"Why are there so many Datadog results that I match heavily with —
is there skewing happening in the K-means clustering model?"*

Answer: **yes, there is structural skew, and it has three compounding causes.**
None of them mean Datadog is wrong to rank well — its NYC platform/infra roles
plausibly do fit the resume — but the *magnitude* (Datadog #1 of all companies
on day 1 at 95.1, #2 on day 2 at 88.5, with 7 postings in the top table both
days) is inflated by design artifacts, not evidence.

## Evidence from the 2026-06-12 run

64 post-filter jobs were scored, clustered into 4 K-means clusters:

| Cluster | Jobs | Mean fit | Range | Who's in it |
|---------|------|----------|-------|-------------|
| 0 | 13 | 25.0 | 20.5–42.1 | Spotify (8), D. E. Shaw (3), Millennium (2) |
| 1 | 11 | 51.1 | 40.6–64.0 | Anthropic (8), Asana (3) |
| 2 | 11 | 66.1 | 49.9–78.0 | Amazon (6), Compass (2), Ramp (2), Chainalysis (1) |
| 3 | **29 (45%)** | **76.4** | 55.5–100.0 | **All 7 Datadog** + Zocdoc, Etsy, Justworks, Gemini, MongoDB, Lyft, Compass, Mercury, Alloy, DoorDash, Chainalysis |

14 of the top 15 jobs by fit are in cluster 3.

## Cause 1 — scoring runs on a tiny, post-filter corpus

`pipeline.run()` filters first (64 survivors), then calls `score_jobs()` on
only those (`jobsearch/pipeline.py:106` → `:114`). Consequences:

- **TF-IDF IDF weights are computed from 64 documents.** With `min_df=1` and
  30k features, term statistics are noise. A term appearing in 3 of 64 docs
  gets a meaningful weight swing from one extra posting.
- **K-means gets 4 clusters for 64 points** (`pick_cluster_count` ≈ n/15).
  At this size, clusters mostly recover *company authorship* (boilerplate
  makes a company's postings near-duplicates of each other — note Spotify,
  Anthropic, Datadog each land entirely inside a single cluster), not
  skill-space structure. "Cluster affinity" then partly measures "does your
  resume look like this company's boilerplate."
- Scores aren't comparable across days: the day-1 and day-2 vocabularies are
  different, so 88.5 today ≠ 88.5 yesterday.

**Fix:** vectorize + cluster the **full fetched corpus** (~7,200 postings
pre-filter, post-dedupe), with `min_df=3`–5, then score the filtered subset
inside that space. ~7k docs × 30k features is still < 2s of sklearn time.
Cluster count `n/300` capped at 20 gives clusters that mean something
("ML/recsys", "platform/infra", "fintech backend", …).

## Cause 2 — the mega-cluster uniformly boosts 45% of jobs

`fit = 0.7·cosine(resume, job) + 0.3·cosine(resume, centroid_of_job's_cluster)`.

Every job in cluster 3 receives the *identical* +0.3-weighted bonus. Because
cluster 3 is the "generic NYC senior platform/backend SWE" cluster, its
centroid is naturally the closest to a senior-backend resume — so the bonus is
both large and shared by 29 jobs. Effects:

- Compresses real differences *within* the mega-cluster (a mediocre cluster-3
  job outranks a good cluster-2 job).
- Amplifies whichever company has the most postings in the mega-cluster —
  i.e., Datadog with 7.

**Fixes (combined):**
- With full-corpus clustering (Cause-1 fix), clusters get specific enough that
  the affinity term carries signal again. Keep K-means — but consider
  reducing `CLUSTER_WEIGHT` 0.3 → 0.15, or replacing the shared-bonus with
  *rank-within-cluster* (percentile of the job's cosine among its cluster
  peers), which can't mass-boost a cluster.
- Report the cluster label as a human-readable topic (top centroid terms) so
  skew is visible in the report itself.

## Cause 3 — company boilerplate + top-3 lottery

Two non-clustering amplifiers:

1. **Boilerplate cosine inflation.** Greenhouse `content=true` returns full
   posting HTML. Datadog's postings share large "about Datadog" /
   benefits blocks stuffed with observability, cloud, infrastructure,
   distributed-systems vocabulary — exactly the resume's vocabulary. Every
   Datadog posting gets that similarity bump *before* a word of role-specific
   text is compared. (Etsy/Workday and Amazon descriptions carry much less
   marketing text — note their lower spread.)
   **Fix:** per-company boilerplate stripping — for companies with ≥3
   postings, drop sentences/shingles appearing in >60% of that company's
   postings before vectorizing. Cheap (hash shingles) and surgical.
2. **Top-3 mean rewards posting volume.** `company_fit = mean(top-3 postings)`.
   A company with 7 matching postings draws its best 3 from 7 tickets; a
   company with 1 posting gets no draw at all. Datadog fetched 399 postings
   (3rd-most of any company) and landed 7 matches both days.
   **Fix options:** (a) show `company_fit` with a small-sample marker, or
   (b) shrink toward the global mean (`(Σtop3 + k·μ)/(3 + k)`), or simply
   (c) rank companies by their *single best* posting and show breadth as its
   own column. (c) is the most honest and simplest.

## Experiments to validate (after corpus snapshots exist)

Persist `data/corpus/YYYY-MM-DD.jsonl.gz` (all fetched postings, pre-filter,
with descriptions). Then offline:

1. Re-score 2026-06-12 with full-corpus TF-IDF — does Datadog's mean fit drop
   relative to others? (Expected: yes, modestly.)
2. Re-score with boilerplate stripping — expected: Datadog top-3 mean drops
   5–15 points; role-specific matches (eBPF, data-platform) stay high. The
   roles that *survive* are the genuinely good matches.
3. Ablate the cluster term (weight 0 vs 0.15 vs 0.3) — measure rank stability
   day-over-day; pick the weight that maximizes stability without flattening.
4. Sanity metric for every run: top-10 company entropy. If one company ever
   holds >40% of the top table, print a skew warning in the report.

## What survives the correction (preview)

Even with all fixes, expect Datadog to stay top-5: it posts many genuine NYC
senior platform/infra roles (Linux kernel/eBPF, data platform lakehouse,
infrastructure R&D) that legitimately match a senior backend/platform resume.
The point of the fix is that its *position* will be earned by role text, not
marketing text + volume.
