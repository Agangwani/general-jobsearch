"""Pipeline runner: subprocess log streaming and the /run endpoints."""

import sys
import time

from fastapi.testclient import TestClient

from webapp.app import create_app
from webapp.runner import PipelineRunner


def _wait(runner, timeout=10.0):
    deadline = time.time() + timeout
    while runner.exit_code is None and time.time() < deadline:
        time.sleep(0.05)


def test_runner_streams_lines_and_exit_code(tmp_path):
    runner = PipelineRunner(tmp_path, cmd=[
        sys.executable, "-c",
        "import sys; print('  Google: 5 postings'); "
        "print('  Meta: ERROR x', file=sys.stderr)"])
    assert runner.start()
    _wait(runner)
    assert runner.exit_code == 0
    assert "  Google: 5 postings" in runner.lines
    assert "  Meta: ERROR x" in runner.lines  # stderr merged in
    snap = runner.snapshot(since=1)
    assert snap["next"] == 2 and len(snap["lines"]) == 1


def test_runner_rejects_concurrent_start(tmp_path):
    runner = PipelineRunner(tmp_path, cmd=[
        sys.executable, "-c", "import time; time.sleep(5)"])
    assert runner.start()
    assert not runner.start()  # already running
    runner._proc.kill()


def test_run_endpoints_stream_and_autoingest(tmp_path):
    (tmp_path / "data").mkdir()
    app = create_app(tmp_path, db_path=tmp_path / "data" / "test.db")
    app.state.runner._cmd = [sys.executable, "-c", "print('  Datadog: 9 postings')"]
    client = TestClient(app)

    assert client.post("/run").status_code == 200
    _wait(app.state.runner)
    snap = client.get("/run/log?since=0").json()
    assert not snap["running"] and snap["exit_code"] == 0
    text = "\n".join(snap["lines"])
    assert "Datadog: 9 postings" in text
    # no reports/latest.json in tmp root → auto-ingest surfaces its failure
    # in the log rather than silently doing nothing
    assert "Ingest" in text
