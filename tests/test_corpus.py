from datetime import datetime, timezone

from jobsearch.corpus import load_snapshot, write_snapshot
from jobsearch.models import JobPosting


def make_job(i: int) -> JobPosting:
    return JobPosting(
        company="Acme", title=f"Engineer {i}", location="New York, NY",
        url=f"https://example.com/{i}", job_id=str(i),
        description=f"Build system {i}.",
        posted_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        source="test",
    )


def test_snapshot_roundtrip(tmp_path):
    jobs = [make_job(i) for i in range(5)]
    path = write_snapshot(jobs, tmp_path)
    loaded = load_snapshot(path)
    assert len(loaded) == 5
    assert loaded[0].company == "Acme"
    assert loaded[0].description == "Build system 0."
    assert loaded[0].posted_at.year == 2026


def test_snapshot_retention(tmp_path):
    for day in range(1, 6):
        (tmp_path / f"2026-06-0{day}.jsonl.gz").write_bytes(b"")
    write_snapshot([make_job(0)], tmp_path, retention_days=3)
    remaining = sorted(p.name for p in tmp_path.glob("*.jsonl.gz"))
    assert len(remaining) == 3
    assert remaining[-1].endswith(".jsonl.gz")  # today's snapshot survives
    assert "2026-06-01.jsonl.gz" not in remaining
