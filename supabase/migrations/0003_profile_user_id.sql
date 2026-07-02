-- Stage 2b (part 1): per-user profile isolation.
-- Add user_id and switch uniqueness from global (field) to per-user
-- (user_id, field). Existing rows default to the local owner. Matches
-- webapp/db.py:SCHEMA for fresh databases.
ALTER TABLE profile_fields ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE profile_fields DROP CONSTRAINT IF EXISTS profile_fields_field_key;
ALTER TABLE profile_fields ADD CONSTRAINT profile_fields_user_id_field_key UNIQUE (user_id, field);
