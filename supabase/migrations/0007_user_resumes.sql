-- Stage 2b: per-user résumé text (existing hosted DBs; fresh databases get
-- this table from webapp/db.py:SCHEMA via sqlite_schema_to_postgres).
-- The résumé was a single on-disk file (data/resume.txt). Hosted disk is
-- ephemeral and multi-user, so each user's résumé text lives here — needed so
-- the daily worker can re-score every active user against the fresh corpus, and
-- so an uploaded résumé survives a container restart. New table, additive.

CREATE TABLE IF NOT EXISTS user_resumes (
    user_id     TEXT PRIMARY KEY DEFAULT 'local',
    resume_text TEXT NOT NULL DEFAULT '',
    pdf_name    TEXT DEFAULT '',
    updated_at  TEXT NOT NULL
);
