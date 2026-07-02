# tests/ — testing protocol

Run with `python -m pytest -q` (pytest defaults; no config file). Offline — no network needed.
`tests/fixtures/resumes/` holds 20 industry resumes behind `test_industry_resumes.py`.

## Rules
- Every behavior change ships a **fails-before / passes-after** regression test. Confirm it
  actually fails when the fix is reverted — a test that passes without the fix proves nothing.
- **One root cause per change.** Don't edit unrelated failing tests. Exception: refresh a
  genuinely stale test whose assertion no longer matches hardened behavior (e.g. an
  end-to-end self-test asserting a bug that's since been fixed) instead of leaving it red.
- **Collection integrity.** After merging parallel agent branches, confirm the suite still
  *collects*: no `<<<<<<<`/`=======`/`>>>>>>>` conflict markers, no docstring-only/empty test
  bodies, no test that cascaded into its neighbor. `pytest --collect-only` should be clean
  before you trust a green run.
- Web-route regressions go in `test_webapp.py`; UI-QA harness tests in `test_uiqa.py`.
  Postgres-parity tests auto-skip unless `JOBSEARCH_TEST_DATABASE_URL` is set.
- Keep tests offline and deterministic; don't add tests that hit live boards or the network.
