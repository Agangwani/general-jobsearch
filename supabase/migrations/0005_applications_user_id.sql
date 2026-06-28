-- Stage 2b (part 3): per-user applications (the lazy-application model).
-- An application is one user's engagement with one posting. applications gains
-- user_id and switches uniqueness from global (job_id) to per-user
-- (user_id, job_id), so two accounts can each track the same job independently
-- and the to-apply pile is jobs LEFT JOIN applications scoped to the user.
-- Existing rows default to the local owner. Matches webapp/db.py:SCHEMA for
-- fresh databases. application_events inherit scoping via their application_id
-- FK, and runs (global ingest metadata) stay global — neither needs user_id.

ALTER TABLE applications ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_job_id_key;
ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_user_job_key;
ALTER TABLE applications ADD CONSTRAINT applications_user_job_key UNIQUE (user_id, job_id);
