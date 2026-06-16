"""Run logging: the targeting section in the report, the structured run-log
artifacts, and the ingest stale-jobs diagnostic. All offline."""

import json
from pathlib import Path

from jobsearch.models import Company, JobPosting
from jobsearch.report import render_markdown, write_run_log


def _job(company, title, fit=80.0):
    return JobPosting(company=company, title=title, location="New York, NY",
                      url="https://x/1", job_id="1", fit_score=fit, rank_score=fit)


def test_report_header_and_targeting_section_reflect_the_role():
    jobs = [_job("Gainsight", "Senior Customer Success Manager")]
    targeting = {"occupations": ["Customer Success Manager", "Management Consultant"],
                 "query": "customer success", "seniority": "leadership",
                 "matched_via": "tfidf", "skills": ["account management", "onboarding"],
                 "title_include": 9, "title_exclude": 9}
    md = render_markdown(jobs, {"Gainsight": 80.0}, [Company("Gainsight", "greenhouse")],
                         manual_check=[], errors=[], top_jobs=10, targeting=targeting)
    assert "Customer Success Manager / Management Consultant Report" in md
    assert "What this run targeted" in md
    assert "`customer success`" in md
    assert "account management" in md
    # The old hard-coded SWE headline must be gone.
    assert "Senior Software Engineer Job Report" not in md


def test_report_targeting_off_note():
    md = render_markdown([_job("Acme", "Engineer")], {"Acme": 50.0},
                         [Company("Acme", "greenhouse")], manual_check=[], errors=[],
                         top_jobs=10, targeting={"mode": "manual", "query": "x"})
    assert "Role targeting **off**" in md


def test_report_no_targeting_is_backward_compatible():
    md = render_markdown([_job("Acme", "Engineer")], {"Acme": 50.0},
                         [Company("Acme", "greenhouse")], manual_check=[], errors=[],
                         top_jobs=10)
    assert "Job Report —" in md
    assert "What this run targeted" not in md


def test_write_run_log_emits_json_and_markdown(tmp_path):
    runlog = {
        "generated": "2026-06-13T12:00:00+00:00",
        "resume": {"source": "data/resume.txt", "chars": 1840},
        "targeting": {"occupations": ["Customer Success Manager"], "query": "customer success",
                      "seniority": "leadership", "matched_via": "tfidf",
                      "skills": ["account management"], "title_include": 9, "title_exclude": 9},
        "companies": {"enabled": 59, "with_postings": ["Stripe", "Gainsight"],
                      "zero_fetch": ["Etsy"], "errored": [{"company": "Meta", "error": "403"}]},
        "totals": {"fetched": 7890, "matched": 12, "near_miss": 30},
        "top_jobs": [{"company": "Gainsight", "title": "Senior CSM",
                      "location": "NYC", "fit": 100.0, "rank_score": 90.0}],
    }
    path = write_run_log(tmp_path, runlog)
    assert path.name == "run-log.json"
    loaded = json.loads(path.read_text())
    assert loaded["targeting"]["query"] == "customer success"
    assert loaded["totals"]["matched"] == 12

    md = (tmp_path / "run-log.md").read_text()
    assert "Customer Success Manager" in md
    assert "Matched: 12" in md
    assert "Gainsight · Senior CSM" in md
    assert "Meta" in md  # errored board surfaced
