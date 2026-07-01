-- Stage 2b (part 4b): per-user résumé text.
-- The résumé was a single on-disk file (data/resume.txt). Hosted disk is
-- ephemeral and multi-user, so each user's résumé text lives here — needed so
-- the daily worker can re-score every active user against the fresh corpus, and
-- so an uploaded résumé survives a container restart. New table, additive.

CREATE TABLE IF NOT EXISTS user_resumes (
    user_id     TEXT PRIMARY KEY,
    resume_text TEXT NOT NULL DEFAULT '',
    filename    TEXT DEFAULT '',
    updated_at  TEXT NOT NULL
);
