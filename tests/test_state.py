from jobsearch.models import JobPosting
from jobsearch.state import load_seen, mark_new, update_seen


def job(key_id: str) -> JobPosting:
    return JobPosting(company="X", title="t", location="NY", url="", job_id=key_id, source="test")


def test_roundtrip(tmp_path):
    path = tmp_path / "seen.tsv"
    jobs = [job("1"), job("2")]
    seen = load_seen(path)
    assert seen == {}
    mark_new(jobs, seen)
    assert all(j.is_new for j in jobs)
    update_seen(jobs, seen, path)

    seen2 = load_seen(path)
    assert len(seen2) == 2
    mark_new(jobs, seen2)
    assert not any(j.is_new for j in jobs)


def test_salvages_corrupt_merge(tmp_path):
    """A botched git merge (conflict markers committed) must not reset state —
    this exact failure made every job 🆕 on 2026-06-12."""
    path = tmp_path / "seen.tsv"
    path.write_text(
        "<<<<<<< HEAD\n"
        "test:X:1\t2026-06-11\n"
        "=======\n"
        "test:X:2\t2026-06-12\n"
        ">>>>>>> other\n"
        "test:X:3\t2026-06-12\n"
    )
    seen = load_seen(path)
    assert seen == {"test:X:1": "2026-06-11", "test:X:2": "2026-06-12", "test:X:3": "2026-06-12"}


def test_migrates_legacy_json(tmp_path):
    legacy = tmp_path / "seen.json"
    legacy.write_text('{\n"test:X:1": "2026-06-10",\n"test:X:2": "2026-06-11"\n}\n')
    seen = load_seen(tmp_path / "seen.tsv")  # tsv missing -> reads .json sibling
    assert seen == {"test:X:1": "2026-06-10", "test:X:2": "2026-06-11"}


def test_salvages_corrupt_legacy_json(tmp_path):
    legacy = tmp_path / "seen.json"
    legacy.write_text(
        '{\n<<<<<<< HEAD\n"test:X:1": "2026-06-11",\n=======\n"test:X:2": "2026-06-12",\n>>>>>>> theirs\n}\n'
    )
    seen = load_seen(tmp_path / "seen.tsv")
    assert seen == {"test:X:1": "2026-06-11", "test:X:2": "2026-06-12"}
