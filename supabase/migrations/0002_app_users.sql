-- Hosted-mode accounts (Supabase Auth). `id` is the Supabase auth user UUID.
-- Mirrors the app_users table in webapp/db.py:SCHEMA so the local SQLite schema
-- and the hosted Postgres schema stay in lockstep. Per-user data isolation
-- (user_id on the per-user tables, user_job_fit) arrives in a later migration.
CREATE TABLE IF NOT EXISTS app_users (
    id            TEXT PRIMARY KEY,            -- Supabase auth user id (UUID)
    email         TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);
