# webapp/ — FastAPI tracker rules

`create_app()` in `app.py`; Jinja2 `templates/` + `static/`. SQLite (`db.py`) by default,
Postgres (`pgcompat.py`) when `JOBSEARCH_DATABASE_URL` is set.

`create_app` reads `config/settings.yaml` at startup — guard for a missing file in tests.

## Routes must never 500 on bad input — IMPORTANT
Every handler that parses/binds user input (path params, query params, form fields, file
uploads) must degrade gracefully (not-found / empty / no-op), never raise HTTP 500. This is the
repo's single most recurring bug class. Specifically handle:
- **IDs outside signed int64** (≥ 2⁶³): bound-check before binding into the DB, else
  `OverflowError`. When you fix this, fix *every* copy — inline queries in other handlers get missed.
- **Non-numeric numeric params** (`?min_fit=abc`): `try/except` → treat as no filter.
- **Stale/unknown IDs on state-change POSTs**: pre-check the row exists (`_require_row`-style)
  before an INSERT that has an FK — don't rely on catching `IntegrityError` after the fact.
- **File uploads**: `pypdf` raises `PdfError`, not `ValueError` — translate before an
  `except ValueError` will catch it.
- **SQL `LIKE` metacharacters**: escape user input with a `like_term()` helper + `ESCAPE '\'`;
  never interpolate `f"%{q}%"` raw (`q='%'` matches everything).

## DB code must be dialect-agnostic (SQLite + Postgres)
- **Prevent errors (existence checks) rather than catch backend-specific exceptions.** Catching
  only `sqlite3.Error` misses `psycopg.Error`, and a failed statement poisons the Postgres
  transaction.
- Local single-user mode (no `SUPABASE_URL` / `JOBSEARCH_DATABASE_URL`) must stay byte-for-byte
  unchanged. Postgres-parity tests auto-skip without `JOBSEARCH_TEST_DATABASE_URL`.

## Template / front-end hygiene
- Use **`quote`/`qpath`** (safe=`""`) for URL **path segments**; `quote_plus` only for query
  strings (`+` is literal in a path → `/companies/goldman+sachs` breaks).
- Don't render controls that can't work: guard URL-less jobs with `{% if job.url %}` (no
  `href=""`, no apply buttons that 404).
- `target=_blank` links need `rel="noopener"`. Clipboard writes need `.catch()` + an
  `execCommand` fallback. Overlapping decorative SVG needs `pointer-events:none`.

New/changed routes get a regression test in `tests/test_webapp.py`; validate fixes with
`python -m uiqa replay --id <finding>`.
