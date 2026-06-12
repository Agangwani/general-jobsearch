import json
from datetime import datetime, timedelta, timezone

from jobsearch.models import JobPosting
from jobsearch.validation import (
    MISMATCH,
    STALE,
    VERIFIED,
    apply_verdicts,
    archive_validation,
    load_verdicts,
    write_validation_request,
)


def job(jid: str, **kw) -> JobPosting:
    defaults = dict(company="Acme", title="Senior Software Engineer",
                    location="New York, NY", url=f"https://example.com/{jid}",
                    job_id=jid, source="test")
    defaults.update(kw)
    return JobPosting(**defaults)


def test_write_request(tmp_path):
    near = job("n1", title="Backend Engineer")
    near.filter_reason = "UNLEVELED_TITLE"
    path = write_validation_request([job("1"), job("2")], [near], tmp_path / "req.md")
    text = path.read_text()
    assert "test:Acme:1" in text
    assert "UNLEVELED_TITLE" in text
    assert "data/validation.json" in text  # schema instructions present


def write_verdict_file(path, checked_at, verdicts):
    path.write_text(json.dumps({"checked_at": checked_at, "verdicts": verdicts}))


def test_verdict_statuses(tmp_path):
    now = datetime.now(timezone.utc)
    path = tmp_path / "validation.json"
    write_verdict_file(path, now.isoformat(), [
        {"key": "test:Acme:1", "live": True, "senior_confirmed": True, "nyc_confirmed": True},
        {"key": "test:Acme:2", "live": True, "nyc_confirmed": False,
         "flags": ["multi-state remote pool"]},
        {"key": "test:Acme:3", "live": False},
    ])
    verdicts = load_verdicts(path, now=now)
    jobs = [job("1"), job("2"), job("3"), job("4")]
    tally = apply_verdicts(jobs, verdicts)
    assert jobs[0].validation == VERIFIED
    assert jobs[1].validation == MISMATCH and "remote pool" in jobs[1].validation_note
    assert jobs[2].validation == STALE
    assert jobs[3].validation == ""  # unchecked
    assert tally == {VERIFIED: 1, MISMATCH: 1, STALE: 1}


def test_expired_verdicts_dropped(tmp_path):
    now = datetime.now(timezone.utc)
    path = tmp_path / "validation.json"
    write_verdict_file(path, (now - timedelta(days=10)).isoformat(),
                       [{"key": "test:Acme:1", "live": True}])
    assert load_verdicts(path, now=now) == {}


def test_corrupt_verdicts_ignored(tmp_path):
    path = tmp_path / "validation.json"
    path.write_text("{not json")
    assert load_verdicts(path) == {}


def test_archive(tmp_path):
    path = tmp_path / "validation.json"
    write_verdict_file(path, "2026-06-13T09:00:00Z", [{"key": "k", "live": True}])
    history = tmp_path / "history"
    archive_validation(path, history)
    assert (history / "2026-06-13.json").exists()
    archive_validation(path, history)  # idempotent
    assert len(list(history.glob("*.json"))) == 1
