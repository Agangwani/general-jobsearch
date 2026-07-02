-- Stage 2a: per-user data isolation for the job/application/startup layer.
-- jobs and startup_companies gain user_id and switch uniqueness from global
-- (key / company_key) to per-user. Existing rows default to the local owner.
-- Matches webapp/db.py:SCHEMA for fresh databases; the SQLite path applies the
-- additive column top-up in db._migrate (it cannot drop an inline UNIQUE, which
-- is harmless with a single local user). applications stay scoped through their
-- jobs join, so they need no user_id column.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_key_key;
ALTER TABLE jobs ADD CONSTRAINT jobs_user_key_key UNIQUE (user_id, key);

ALTER TABLE startup_companies ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE startup_companies DROP CONSTRAINT IF EXISTS startup_companies_company_key_key;
ALTER TABLE startup_companies ADD CONSTRAINT startup_companies_user_company_key_key UNIQUE (user_id, company_key);
