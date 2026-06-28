-- Stage 2b (part 2): per-user prep & company progress.
-- Each progress table gains user_id and switches uniqueness from global (fk) to
-- per-user (user_id, fk). Existing rows default to the local owner. Matches
-- webapp/db.py:SCHEMA for fresh databases.

ALTER TABLE prep_lesson_progress ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE prep_lesson_progress DROP CONSTRAINT IF EXISTS prep_lesson_progress_lesson_id_key;
ALTER TABLE prep_lesson_progress ADD CONSTRAINT prep_lesson_progress_user_lesson_key UNIQUE (user_id, lesson_id);

ALTER TABLE prep_problem_progress ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE prep_problem_progress DROP CONSTRAINT IF EXISTS prep_problem_progress_problem_id_key;
ALTER TABLE prep_problem_progress ADD CONSTRAINT prep_problem_progress_user_problem_key UNIQUE (user_id, problem_id);

ALTER TABLE prep_ctci_problem_progress ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE prep_ctci_problem_progress DROP CONSTRAINT IF EXISTS prep_ctci_problem_progress_ctci_problem_id_key;
ALTER TABLE prep_ctci_problem_progress ADD CONSTRAINT prep_ctci_problem_progress_user_ctci_key UNIQUE (user_id, ctci_problem_id);

ALTER TABLE company_problem_progress ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE company_problem_progress DROP CONSTRAINT IF EXISTS company_problem_progress_company_problem_id_key;
ALTER TABLE company_problem_progress ADD CONSTRAINT company_problem_progress_user_cpid_key UNIQUE (user_id, company_problem_id);
