"""Seed the authored prep content (``ALL_TRACKS``) into the prep_* tables.

Called once on every UI start (``webapp/app.py``). Two properties matter:

- **Idempotent.** A content hash is stamped in ``prep_meta``; if the content
  hasn't changed and the tables are populated, the seed is a no-op.
- **Progress-preserving.** Tracks/modules/lessons/problems are UPSERTed by
  their *stable natural keys* (slugs), so a row keeps its integer ``id`` across
  reseeds. The progress tables (``prep_lesson_progress``,
  ``prep_problem_progress``) reference those ids, so editing or re-seeding the
  content never wipes how far the user has gotten. Rows that disappear from the
  content (a renamed slug, a deleted lesson) are pruned — and their orphaned
  progress rows are removed first so the foreign keys stay satisfied.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from . import ALL_TRACKS


def _content_hash(tracks: list[dict]) -> str:
    blob = json.dumps(tracks, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM prep_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _meta_set(conn: sqlite3.Connection, key: str, value: str, now: str) -> None:
    conn.execute(
        """INSERT INTO prep_meta (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (key, value, now))


def seed_into_db(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    """Write ALL_TRACKS into the prep_* tables. Returns a small summary dict.

    No-op (beyond a hash check) when the content is unchanged and already
    seeded, unless ``force=True``.
    """
    from webapp.db import utcnow  # local import: avoid a package import cycle

    now = utcnow()
    content_hash = _content_hash(ALL_TRACKS)
    have_rows = conn.execute("SELECT COUNT(*) AS n FROM prep_tracks").fetchone()["n"]
    if not force and have_rows and _meta_get(conn, "content_hash") == content_hash:
        return {"seeded": False, "reason": "unchanged",
                "tracks": have_rows}

    kept_tracks: set[int] = set()
    kept_modules: set[int] = set()
    kept_lessons: set[int] = set()
    kept_problems: set[int] = set()
    kept_ctci: set[int] = set()

    for t_order, track in enumerate(ALL_TRACKS):
        conn.execute(
            """INSERT INTO prep_tracks (slug, title, description, sort_order)
               VALUES (:slug, :title, :description, :sort_order)
               ON CONFLICT(slug) DO UPDATE SET
                   title = excluded.title,
                   description = excluded.description,
                   sort_order = excluded.sort_order""",
            {"slug": track["slug"], "title": track["title"],
             "description": track.get("description", ""), "sort_order": t_order})
        track_id = conn.execute(
            "SELECT id FROM prep_tracks WHERE slug = ?", (track["slug"],)).fetchone()["id"]
        kept_tracks.add(track_id)

        for m_order, module in enumerate(track.get("modules", [])):
            conn.execute(
                """INSERT INTO prep_modules
                       (track_id, slug, title, summary, source_refs, est_minutes, sort_order)
                   VALUES (:track_id, :slug, :title, :summary, :source_refs,
                           :est_minutes, :sort_order)
                   ON CONFLICT(slug) DO UPDATE SET
                       track_id = excluded.track_id,
                       title = excluded.title,
                       summary = excluded.summary,
                       source_refs = excluded.source_refs,
                       est_minutes = excluded.est_minutes,
                       sort_order = excluded.sort_order""",
                {"track_id": track_id, "slug": module["slug"], "title": module["title"],
                 "summary": module.get("summary", ""),
                 "source_refs": module.get("source_refs", ""),
                 "est_minutes": int(module.get("est_minutes", 30)),
                 "sort_order": m_order})
            module_id = conn.execute(
                "SELECT id FROM prep_modules WHERE slug = ?", (module["slug"],)).fetchone()["id"]
            kept_modules.add(module_id)

            for l_order, lesson in enumerate(module.get("lessons", [])):
                takeaways = json.dumps(lesson.get("key_takeaways", []), ensure_ascii=False)
                conn.execute(
                    """INSERT INTO prep_lessons
                           (module_id, slug, title, body_md, source_refs,
                            key_takeaways, sort_order)
                       VALUES (:module_id, :slug, :title, :body_md, :source_refs,
                               :key_takeaways, :sort_order)
                       ON CONFLICT(module_id, slug) DO UPDATE SET
                           title = excluded.title,
                           body_md = excluded.body_md,
                           source_refs = excluded.source_refs,
                           key_takeaways = excluded.key_takeaways,
                           sort_order = excluded.sort_order""",
                    {"module_id": module_id, "slug": lesson["slug"], "title": lesson["title"],
                     "body_md": lesson["body_md"], "source_refs": lesson.get("source_refs", ""),
                     "key_takeaways": takeaways, "sort_order": l_order})
                lesson_id = conn.execute(
                    "SELECT id FROM prep_lessons WHERE module_id = ? AND slug = ?",
                    (module_id, lesson["slug"])).fetchone()["id"]
                kept_lessons.add(lesson_id)

            for p_order, prob in enumerate(module.get("problems", [])):
                conn.execute(
                    """INSERT INTO prep_problems
                           (module_id, leetcode_number, leetcode_slug, title,
                            difficulty, topic, url, sort_order)
                       VALUES (:module_id, :leetcode_number, :leetcode_slug, :title,
                               :difficulty, :topic, :url, :sort_order)
                       ON CONFLICT(module_id, leetcode_slug) DO UPDATE SET
                           leetcode_number = excluded.leetcode_number,
                           title = excluded.title,
                           difficulty = excluded.difficulty,
                           topic = excluded.topic,
                           url = excluded.url,
                           sort_order = excluded.sort_order""",
                    {"module_id": module_id,
                     "leetcode_number": prob.get("leetcode_number"),
                     "leetcode_slug": prob["leetcode_slug"], "title": prob["title"],
                     "difficulty": prob.get("difficulty", "medium"),
                     "topic": prob.get("topic", ""), "url": prob.get("url", ""),
                     "sort_order": p_order})
                problem_id = conn.execute(
                    "SELECT id FROM prep_problems WHERE module_id = ? AND leetcode_slug = ?",
                    (module_id, prob["leetcode_slug"])).fetchone()["id"]
                kept_problems.add(problem_id)

            for c_order, cprob in enumerate(module.get("ctci_problems", [])):
                hints_json = json.dumps(cprob.get("hints", []), ensure_ascii=False)
                conn.execute(
                    """INSERT INTO prep_ctci_problems
                           (module_id, slug, ctci_id, title, prompt_md,
                            examples_md, hints, solution_md, complexity, sort_order)
                       VALUES (:module_id, :slug, :ctci_id, :title, :prompt_md,
                               :examples_md, :hints, :solution_md, :complexity,
                               :sort_order)
                       ON CONFLICT(module_id, slug) DO UPDATE SET
                           ctci_id = excluded.ctci_id,
                           title = excluded.title,
                           prompt_md = excluded.prompt_md,
                           examples_md = excluded.examples_md,
                           hints = excluded.hints,
                           solution_md = excluded.solution_md,
                           complexity = excluded.complexity,
                           sort_order = excluded.sort_order""",
                    {"module_id": module_id, "slug": cprob["slug"],
                     "ctci_id": cprob["ctci_id"], "title": cprob["title"],
                     "prompt_md": cprob["prompt_md"],
                     "examples_md": cprob.get("examples_md", ""),
                     "hints": hints_json,
                     "solution_md": cprob["solution_md"],
                     "complexity": cprob.get("complexity", ""),
                     "sort_order": c_order})
                cp_id = conn.execute(
                    "SELECT id FROM prep_ctci_problems WHERE module_id = ? AND slug = ?",
                    (module_id, cprob["slug"])).fetchone()["id"]
                kept_ctci.add(cp_id)

    _prune(conn, "prep_problem_progress", "problem_id", "prep_problems", kept_problems)
    _prune(conn, "prep_ctci_problem_progress", "ctci_problem_id",
           "prep_ctci_problems", kept_ctci)
    _prune(conn, "prep_lesson_progress", "lesson_id", "prep_lessons", kept_lessons)
    _prune_table(conn, "prep_modules", kept_modules)
    _prune_table(conn, "prep_tracks", kept_tracks)

    _meta_set(conn, "content_hash", content_hash, now)
    _meta_set(conn, "seeded_at", now, now)
    conn.commit()
    return {
        "seeded": True,
        "tracks": len(kept_tracks),
        "modules": len(kept_modules),
        "lessons": len(kept_lessons),
        "problems": len(kept_problems),
        "ctci_problems": len(kept_ctci),
    }


def _prune(conn: sqlite3.Connection, progress_table: str, fk_col: str,
           content_table: str, kept_ids: set[int]) -> None:
    """Delete progress rows pointing at content rows we're about to remove,
    so the subsequent content-row delete doesn't trip a foreign key."""
    rows = conn.execute(f"SELECT id FROM {content_table}").fetchall()
    stale = [r["id"] for r in rows if r["id"] not in kept_ids]
    for sid in stale:
        conn.execute(f"DELETE FROM {progress_table} WHERE {fk_col} = ?", (sid,))
    for sid in stale:
        conn.execute(f"DELETE FROM {content_table} WHERE id = ?", (sid,))


def _prune_table(conn: sqlite3.Connection, table: str, kept_ids: set[int]) -> None:
    rows = conn.execute(f"SELECT id FROM {table}").fetchall()
    for r in rows:
        if r["id"] not in kept_ids:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (r["id"],))
