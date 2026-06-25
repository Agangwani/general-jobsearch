"""Tests for the multi-discipline prep curriculum: content integrity, seeding,
the occupation→discipline mapping, and the per-resume track recommendations.

The prep content is the one part of the flow that is *not* filtered away per
resume — every track is available to everyone. What IS tailored is which tracks
are *recommended*: the universal Behavioral track for every resume, plus the
discipline-specific track(s) for the resume's occupation.
"""

from pathlib import Path

import pytest

from jobsearch.prep import ALL_TRACKS, TRACK_BEHAVIORAL
from jobsearch.prep.disciplines import (
    GENERAL,
    OCCUPATION_DISCIPLINES,
    disciplines_for_occupations,
    split_tracks,
    track_is_relevant,
)
from jobsearch.prep.seed import seed_into_db
from jobsearch.role_profile import build_profile, load_occupations

from tests.industry_fixtures import FIXTURES

OCC_PATH = Path(__file__).resolve().parent.parent / "config" / "occupations.yaml"
OCCUPATIONS = load_occupations(OCC_PATH)
IDS = [f.slug for f in FIXTURES]

# Disciplines that own at least one non-behavioral track.
_TRACK_DISCIPLINES = {d for t in ALL_TRACKS for d in (t.get("disciplines") or [])}


# ----------------------------------------------------------------- content

def test_expected_tracks_present():
    slugs = {t["slug"] for t in ALL_TRACKS}
    # The original software tracks survive...
    assert {"coding", "system-design", "distributed-systems"} <= slugs
    # ...and the new discipline tracks are added.
    assert {"behavioral", "case-interview", "finance", "product-management",
            "data-analytics", "sales-cs", "marketing", "design",
            "industry-interviews"} <= slugs


def test_track_content_is_well_formed():
    track_slugs, module_slugs, lesson_keys = set(), set(), set()
    for track in ALL_TRACKS:
        assert track["slug"] and track["title"] and track["description"]
        assert track.get("disciplines"), f"{track['slug']} declares no disciplines"
        assert track["slug"] not in track_slugs
        track_slugs.add(track["slug"])
        assert track["modules"], f"{track['slug']} has no modules"
        for module in track["modules"]:
            assert module["slug"] not in module_slugs, f"dup module {module['slug']}"
            module_slugs.add(module["slug"])
            for lesson in module.get("lessons", []):
                key = (module["slug"], lesson["slug"])
                assert key not in lesson_keys, f"dup lesson {key}"
                lesson_keys.add(key)
                assert lesson["body_md"].strip(), f"empty body {key}"
                assert lesson.get("source_refs"), f"no source on {key}"
                assert lesson.get("key_takeaways"), f"no takeaways on {key}"


def test_behavioral_track_is_universal():
    assert TRACK_BEHAVIORAL["disciplines"] == [GENERAL]
    # And it carries real, substantial content (the centerpiece of the request).
    lessons = sum(len(m.get("lessons", [])) for m in TRACK_BEHAVIORAL["modules"])
    assert lessons >= 10
    # STAR and Amazon Leadership Principles are covered.
    blob = "\n".join(l["body_md"] for m in TRACK_BEHAVIORAL["modules"]
                     for l in m.get("lessons", [])).lower()
    assert "situation" in blob and "task" in blob and "action" in blob and "result" in blob
    assert "leadership principle" in blob


def test_case_interview_track_for_consulting():
    """The explicitly-requested case-interview content exists and covers the
    canonical material (MECE, frameworks, market sizing)."""
    case = next(t for t in ALL_TRACKS if t["slug"] == "case-interview")
    assert "consulting" in case["disciplines"]
    parts = []
    for module in case["modules"]:
        parts += [module["title"], module.get("summary", "")]
        for lesson in module.get("lessons", []):
            parts += [lesson["title"], lesson["body_md"]]
    blob = "\n".join(parts).lower()
    for term in ("mece", "profitability", "market entry", "market sizing"):
        assert term in blob, f"case track missing {term!r}"


def test_all_tracks_seed_into_db_idempotently(tmp_path):
    from webapp.db import connect

    conn = connect(tmp_path / "prep.db")
    summary = seed_into_db(conn)
    assert summary["seeded"] and summary["tracks"] == len(ALL_TRACKS)
    assert summary["lessons"] >= 100
    # Reseed is a no-op (content hash unchanged) — progress-preserving.
    assert seed_into_db(conn)["seeded"] is False
    assert conn.execute("SELECT COUNT(*) n FROM prep_tracks").fetchone()["n"] == len(ALL_TRACKS)


# ------------------------------------------------- occupation → discipline map

def test_every_occupation_maps_to_a_discipline():
    """Every occupation in the taxonomy has a discipline, so no resume is left
    without a recommended specialty track."""
    for occ in OCCUPATIONS:
        assert occ.name in OCCUPATION_DISCIPLINES, f"no discipline for {occ.name!r}"
        assert OCCUPATION_DISCIPLINES[occ.name], f"empty disciplines for {occ.name!r}"


def test_every_mapped_discipline_has_a_track():
    """Every discipline an occupation maps to is served by some track, so
    recommendations are never empty."""
    used = {d for ds in OCCUPATION_DISCIPLINES.values() for d in ds}
    for discipline in used:
        assert discipline in _TRACK_DISCIPLINES, f"no track serves discipline {discipline!r}"


def test_disciplines_for_occupations_always_includes_general():
    assert disciplines_for_occupations([]) == [GENERAL]
    discs = disciplines_for_occupations(["Software Engineer"])
    assert discs[0] == GENERAL and "software" in discs


def test_track_is_relevant_rules():
    assert track_is_relevant(["general"], [])           # behavioral: universal
    assert track_is_relevant([], ["finance"])           # untagged: never hidden
    assert track_is_relevant(["finance"], ["general", "finance"])
    assert not track_is_relevant(["finance"], ["general", "software"])


# ------------------------------------------- per-resume recommendations

# discipline -> the track slugs that serve it (derived from the content).
def _tracks_for_discipline(discipline: str) -> set[str]:
    return {t["slug"] for t in ALL_TRACKS if discipline in (t.get("disciplines") or [])}


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_behavioral_recommended_for_every_resume(fixture):
    """Behavioral prep is recommended for every industry — it's universal."""
    profile = build_profile(fixture.resume_text(), OCCUPATIONS, backend="tfidf")
    discs = disciplines_for_occupations(profile.occupations)
    tracks = [dict(t) for t in ALL_TRACKS]
    recommended, _ = split_tracks(tracks, discs)
    rec_slugs = {t["slug"] for t in recommended}
    assert "behavioral" in rec_slugs, f"{fixture.slug}: behavioral not recommended"


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_discipline_track_recommended_for_its_resume(fixture):
    """Each resume's discipline-specific track is recommended for it (e.g. the
    consulting resume gets Case Interviews; the nurse gets Industry-Specific)."""
    profile = build_profile(fixture.resume_text(), OCCUPATIONS, backend="tfidf")
    discs = disciplines_for_occupations(profile.occupations)
    assert fixture.discipline in discs, (
        f"{fixture.slug}: expected discipline {fixture.discipline!r} not in {discs}")

    recommended, _ = split_tracks([dict(t) for t in ALL_TRACKS], discs)
    rec_slugs = {t["slug"] for t in recommended}
    owning = _tracks_for_discipline(fixture.discipline)
    assert owning & rec_slugs, (
        f"{fixture.slug}: no track for discipline {fixture.discipline!r} recommended "
        f"(have {rec_slugs})")


def test_prep_catalog_is_universal_not_filtered():
    """Tailoring only re-orders prep; it never removes tracks. Even with a narrow
    (finance) resume, every track is still present — recommended ∪ other == all."""
    discs = ["general", "finance"]
    recommended, other = split_tracks([dict(t) for t in ALL_TRACKS], discs)
    all_slugs = {t["slug"] for t in ALL_TRACKS}
    assert {t["slug"] for t in recommended} | {t["slug"] for t in other} == all_slugs
    # The software tracks remain available (in 'other') for a finance resume.
    assert "coding" in {t["slug"] for t in other}


def test_software_resume_recommended_coding_not_finance():
    """Sanity on the split direction: a software resume highlights coding, and
    finance lands in 'other'."""
    discs = disciplines_for_occupations(["Software Engineer"])
    recommended, other = split_tracks([dict(t) for t in ALL_TRACKS], discs)
    rec, oth = {t["slug"] for t in recommended}, {t["slug"] for t in other}
    assert "coding" in rec and "behavioral" in rec
    assert "finance" in oth
