# Validation Loop: Confidence Scores Without the Claude API

Questions: *"What's the confidence level in the jobs we're creating? Should we
add a validation step that cross-checks results via a Claude prompt and an
input file? I don't want to use the Claude API since I have the monthly
subscription, but I can, once a day, ask Claude to take a file and search the
web. Is that the best solution?"*

## Short answer

Yes — with one refinement. A once-daily "Claude reads a file and searches the
web" pass is the right semantic check, and running it **inside Claude Code as
a repo slash command** (subscription-funded, zero API cost) is strictly better
than pasting into claude.ai, because Claude Code can also *write the verdicts
back into the repo* where the next run merges them automatically.

But don't make Claude do work a script can do for free. Use two tiers:

## Tier 1 — automated checks, every run, no Claude involved

Cheap, deterministic data-quality scoring computed during `python -m jobsearch run`:

| Check | Signal |
|-------|--------|
| Apply URL returns HTTP 200 (HEAD/GET, capped concurrency) | posting is live |
| URL is on a company-owned or first-party ATS domain | direct-apply requirement holds |
| Posted date present and ≤ max_age | recency math is real, not the unknown-age default |
| Description length > ~300 chars | fit score is based on content, not just a title |
| Title contains explicit seniority | not an inferred/unleveled match |
| Board freshness (company's newest posting < 30 days old) | board isn't a graveyard |

These fold into a 0–1 `data_confidence` per job, shown in the report
(e.g. ●●●○○). Catches dead links and thin matches **before** any human or
Claude time is spent.

## Tier 2 — Claude semantic validation, once a day, subscription-funded

What only a web-searching reviewer can verify: is the role *really* senior,
*really* NYC, still open, and does the team/stack match the resume?

### The loop

```
1. python -m jobsearch run                    (writes reports/latest.json)
   └─ also writes reports/validation-request.md   ← compact, Claude-ready

2. You (once a day, in Claude Code):  /validate-jobs
   └─ Claude reads validation-request.md, web-searches each posting,
      writes data/validation.json

3. Next python -m jobsearch run (or `merge-validation` subcommand)
   └─ merges verdicts → report gains a Confidence column:
      ✓ verified · ⚠ mismatch (with note) · ✗ stale/dead · ? unchecked
```

### `reports/validation-request.md` (generated)

Top ~15 jobs by rank score (the ones you'd actually apply to), each with the
claims to verify:

```markdown
## 1. Datadog — Senior Software Engineer, Code Gen
- url: https://careers.datadoghq.com/detail/7993198/
- claims: still-open | senior-level | NYC-based or NYC-hybrid | posted ~2026-06-10
- resume-fit claim: platform/codegen work matches infra+backend background
```

### `data/validation.json` (written by Claude, consumed by the pipeline)

```json
{
  "checked_at": "2026-06-13T09:00:00Z",
  "verdicts": [
    {
      "key": "greenhouse:Datadog:7993198",
      "live": true,
      "senior_confirmed": true,
      "nyc_confirmed": true,
      "fit_assessment": "strong — role is build-tooling/codegen, matches platform background",
      "flags": [],
      "confidence": 0.9
    },
    {
      "key": "ashby:Chainalysis:19072991",
      "live": true,
      "senior_confirmed": true,
      "nyc_confirmed": false,
      "flags": ["location is 'Massachusetts, New York, Virginia…' — multi-state remote pool, not NYC office"],
      "confidence": 0.5
    }
  ]
}
```

(The Chainalysis example is real — today's #1 fit (100.0) lists six states,
which is exactly the kind of thing Tier 2 catches and Tier 1 can't.)

### Ship it as a repo slash command

`.claude/commands/validate-jobs.md` — checked into the repo so the workflow is
one keystroke (`/validate-jobs`) in any Claude Code session. The command
instructs Claude to: read `reports/validation-request.md`, verify each posting
via web search (posting page live? title/level/location as claimed? any
"no longer accepting applications" banner?), then write `data/validation.json`
in the schema above and commit it.

### Why not the alternatives

| Option | Verdict |
|--------|---------|
| Claude API in the GitHub Action | Rejected by requirement (per-token cost on top of subscription) |
| Paste report into claude.ai daily | Works (good fallback on mobile), but verdicts don't land back in the repo — you'd re-paste results manually |
| **Claude Code slash command** | **Chosen** — subscription-funded, repo-aware, writes the file, one command |
| Heuristics only (Tier 1 alone) | Free but can't verify level/location/liveness semantics — misses the Chainalysis-style errors |

## Confidence model (combined)

```
confidence = data_confidence            (tier 1, every run)
           × validation_multiplier      (tier 2: ✓=1.0, ?=0.8, ⚠=0.5, ✗=0)
```

Report sorts unchanged (fit × recency) but displays confidence, and the
"apply next" shortlist = top jobs with confidence ≥ 0.7. Application
automation (next doc) must only ever draw from that shortlist.
