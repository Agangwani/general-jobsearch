# Documentation index

This folder has two kinds of docs:

- **Reference docs** (new) — describe the system *as it is now*: how it's built,
  how data flows, what every part does, and where it falls short. Start here to
  understand the codebase.
- **Design & analysis docs** (existing) — capture *why* specific decisions were
  made and the investigations behind them. They are dated, often carry a
  shipped/planned **Status** banner, and read as a living engineering log.

## Reference docs — start here

| Doc | What it covers |
|-----|----------------|
| **[architecture.md](architecture.md)** | **Read first.** The whole system on one page: the two halves (pipeline + web app), the end-to-end data flow, the directory map, where every piece of state lives, how the three config files relate, and the mental models that make the code click. |
| [pipeline.md](pipeline.md) | Deep dive on `python -m jobsearch run`: every stage, the fetcher contract, the browser-harvesting core, the TF-IDF + K-means scoring math, the filter logic, the discovery commands, and the report artifacts. |
| [webapp.md](webapp.md) | Deep dive on the FastAPI app: bootstrap, the full route table, the SQLite schema, the integrated apply-browser + autofill engine, Gmail sync, and the prep/questions/referrals subsystems. |
| [user-flows.md](user-flows.md) | Concrete end-to-end journeys (setup, the daily loop, retargeting a résumé, company discovery, the validation loop, prep, referrals, email sync), each traced to the code. |
| [limitations.md](limitations.md) | An honest, consolidated account of what the repo doesn't do well, where it's fragile, and what to watch for. |
| [refactoring.md](refactoring.md) | Prioritized, concrete refactoring proposals (with code references) to pay down specific debt. |

**Suggested reading order:** `architecture.md` → skim `user-flows.md` for the
"why" → `pipeline.md` and/or `webapp.md` for the half you're working in →
`limitations.md` / `refactoring.md` when you're changing something.

## Design & analysis docs — the "why" and the history

| Doc | What it covers | Status |
|-----|----------------|--------|
| [improvement-plan.md](improvement-plan.md) | The v2 roadmap and the master plan the workstreams below hang off; run-3 scoreboard. | mostly shipped |
| [analysis-scoring-skew.md](analysis-scoring-skew.md) | "Why Datadog dominates" — diagnosis + fixes for company-authored text skewing fit scores. | shipped |
| [analysis-zero-match-companies.md](analysis-zero-match-companies.md) | Why some companies returned zero matches (unleveled titles, the "Sr." abbreviation); the funnel + near-miss design. | shipped |
| [design-role-targeting.md](design-role-targeting.md) | Résumé → occupation matching, so a non-SWE résumé stops getting SWE jobs. | shipped |
| [design-company-discovery.md](design-company-discovery.md) | The `discover-companies` command: mining generalized boards for résumé-relevant employers. | shipped |
| [design-validation-loop.md](design-validation-loop.md) | Confidence scores without an API key — the `validation-request.md` → `/validate-jobs` → Conf-column loop. | shipped (Tier-1 auto-checks TODO) |
| [design-frontend.md](design-frontend.md) | The application-tracking UI design + the "Aurora" visual theme. | shipped |
| [design-autofill.md](design-autofill.md) | The "⚡ Auto-fill apply" engine and its never-click-submit contract. | shipped |
| [design-application-automation.md](design-application-automation.md) | The staged roadmap for automating application *submission* (human-in-the-loop). | partial / roadmap |
| [design-deployment.md](design-deployment.md) | Cost analysis of where to run the daily pipeline. | analysis |
| [design-hosting.md](design-hosting.md) | What would change to host the app online for multiple users. | roadmap |

## Beyond `docs/`

- **[../README.md](../README.md)** — the project README: quickstart, "how it
  works," customization, and the layout summary.
- **`config/settings.yaml`** — the keystone config; every knob is commented inline.
- **`future_feature.md`** — a short, informal backlog of user-requested ideas.
- **`tests/`** — ~257 fully-offline tests; reading them is a fast way to learn the
  exact contracts of any module (`test_end_to_end.py` is the best single overview).
