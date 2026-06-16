# Frontend: Application-Tracking UI

> **Status (2026-06-12): v1 shipped.** `python -m jobsearch ui` →
> http://127.0.0.1:8484. Local-only FastAPI + SQLite + a Playwright-driven
> integrated browser for applying.
>
> **Update (2026-06-16): "Aurora" visual redesign.** A ground-up restyle of
> the UI in the spirit of Apple's design language — clarity, deference, depth.
> See **Visual design** below. It is **presentation-only**: no Python, route,
> schema, or data-flow changes, and every JS hook + server-rendered contract
> is preserved, so the sections that follow still describe the system exactly.

## Visual design — "Aurora" (templates + CSS + ~60 lines of vanilla JS)

The look is Apple-inspired and entirely dependency-free (still no node
toolchain). Everything is driven by `webapp/static/app.css`'s design tokens.

- **Type & color.** System-first typography (SF Pro on Apple hardware, Inter
  as the cross-platform fallback), an Apple-blue accent, and a signature
  blue→indigo→violet "aurora" gradient used sparingly (brand mark, the
  *Tracked* stat, progress bars, ring accents). A faint fixed aurora glow sits
  behind the canvas.
- **Light / dark / system.** Tokens cover both modes. The theme follows the OS
  by default and a nav toggle (☾ / ☀) lets the user force light or dark,
  persisted in `localStorage` and applied pre-paint to avoid a flash.
- **Dashboard.** A hero with four clickable, count-up **stat cards** (To apply
  / In progress / Applied / Tracked), an iOS-style **segmented control** for
  switching stacks, and the jobs table reframed as a card. The fit score is
  now an Apple "Activity ring" (a masked `conic-gradient`, colored by tier)
  that fills on load.
- **Motion.** Fluid spring easing, staggered fade-up entrances (driven by a
  `--i` index custom property), hover lift on cards/rows, and cross-page
  **view transitions** where supported. All entrance motion lives under
  `@media (prefers-reduced-motion: no-preference)`, so reduced-motion users
  get the full, static layout.
- **Invariants.** All JS contracts are untouched: `data-apply-btn` /
  `data-refill-btn`, `.row-status`, the bulk-select form, `#run-panel` /
  `#run-pipeline`, `[data-copy]`, and the apply-all controls. Filtering,
  sorting, bulk actions, status changes, and auto-fill behave exactly as before.

## What it is

A local web app for the person *applying* to the jobs the pipeline finds:

- **Two stacks** — "To apply" and "Applied" — backed by an application
  lifecycle (`not_applied → in_progress → applied → confirmed →
  interviewing → offer/rejected/withdrawn`), filterable and searchable
  (title, description, company, location).
- **Job detail** — full description (joined from the local corpus snapshot),
  fit score, validation verdict, filter reason for near-misses, complete
  change history, and linked emails.
- **Integrated apply browser** — "Apply" opens the posting in a headed
  Chromium window (Playwright, persistent profile in `data/browser_profile/`
  so ATS logins survive). Every navigation is watched; a page that looks like
  a submission confirmation automatically flips the application to `applied`
  with the confirming URL recorded. Closing the window without a detection
  leaves it `in_progress` for one-click manual resolution.
- **Copy-paste panel** — profile fields (name, email, links, work auth,
  salary expectation, …) seeded from `data/profile.yaml` + resume parsing,
  editable at `/profile`, click-to-copy on every job page.
- **Resume view** — `/resume` renders `data/resume.txt` block-by-block with
  per-block copy buttons + the PDF inline.
- **Search config view** — `/settings` shows the live title
  include/exclude patterns, locations, and company registry.
- **Email module (scaffold)** — `/emails` ships the schema, the
  message→application matcher, and the classifier; the Gmail OAuth connect
  flow is stubbed with setup instructions (no credentials in the repo, ever).

## Database design (`data/jobsearch.db`, gitignored — holds PII)

```
jobs                 one row per unique posting (pipeline key). first_seen_at =
                     exact UTC insertion time of the discovering run;
                     last_seen_at bumped on re-runs; changed fields patched.
job_events           append-only: inserted / updated{field: [old,new]} / …
applications         1:1 with jobs; the lifecycle + applied_at + submitted_via
application_events   append-only status history (incl. confirmation URLs)
profile_fields       the preloaded copy-paste data
runs                 ingest ledger (inserted/patched counts per run)
email_accounts       gmail connection state
email_messages       append-only, auto-linked to applications, classified
                     (confirmation/interview/rejection/offer/other)
```

Key semantics, per requirements:
- **Insertion date**: `jobs.first_seen_at` is the exact timestamp of the
  ingest that discovered the posting. Multiple runs per day **never
  duplicate** — re-seen jobs only bump `last_seen_at`, and changed values
  (fit score, validation, description…) are patched with the diff recorded
  in `job_events`. Nothing is ever overwritten silently.
- **Append-only history**: every state change of every row is queryable —
  search by company, then read its jobs' and applications' full timelines.
- A detected email confirmation advances `applied → confirmed`
  automatically.

## Data flow

```
python -m jobsearch run          (pipeline: fetch → score → reports/ + corpus snapshot)
python -m jobsearch ingest       (or the ⟳ button in the UI)
        └─ latest.json (matched + near-miss) ⋈ corpus snapshot (descriptions)
           → upsert into jobs / applications, events appended
python -m jobsearch ui           (FastAPI on 127.0.0.1:8484)
        └─ Apply → headed Chromium (Playwright) → confirmation detection
           → application_events / status
```

## Future connections (designed-for, not yet built)

- ~~**Gmail**~~ — **shipped**: raw OAuth loopback flow (no Google SDK) in
  `webapp/gmail.py`. `data/credentials.json` (user-created, gitignored) →
  Connect button → token in `data/token.json` → "⟳ Sync now". The sync query
  is scoped server-side to senders matching companies with an application in
  flight plus ATS platform domains, over the last year — the rest of the
  inbox is never fetched. Older stored mail outside that filter is purged on
  the next sync.
- ~~**Form prefill** (automation Stage 2)~~ — **shipped**: see
  [design-autofill.md](design-autofill.md). The integrated browser is now
  multi-tab and every "⚡ Auto-fill apply" fills the form (never submits).
- Additional providers (calendar for interview scheduling, etc.) follow the
  email pattern: own table(s), append-only, linked to applications.

## Stack & decisions

- **FastAPI + Jinja2 server-rendered + ~80 lines of vanilla JS** — no node
  toolchain in a Python repo; the user is one engineer on localhost.
- **SQLite WAL** — zero-config, perfect for single-user local writes.
- **Playwright headed window** rather than an iframe "browser": job sites
  block framing (X-Frame-Options), and Playwright gives navigation/network
  introspection — which is also the foundation the application-automation
  roadmap (Stage 2/3) builds on, so one browser stack serves both.
- Submission detection is **deliberately conservative** (URL/title/body
  phrases like "application received"); a false `applied` is worse than
  asking the user to confirm manually.
