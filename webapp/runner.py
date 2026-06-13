"""Run the pipeline from the UI, streaming its log.

The pipeline runs as a subprocess (`python -m jobsearch run`) rather than a
thread: it spins up its own thread pool and Playwright Chromium, and a
subprocess keeps all of that — and any crash — isolated from the web app.
Its stderr already narrates per-company progress ("  Google: 20 postings",
"  Meta: ERROR …"), which is exactly what the UI wants to show, so the
runner just buffers merged stdout+stderr lines and the frontend polls for
increments. One run at a time; on success the caller ingests the fresh
report into the database so results appear without a separate step.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path


class PipelineRunner:
    def __init__(self, root: Path, cmd: list[str] | None = None):
        self.root = root
        self._cmd = cmd or [sys.executable, "-u", "-m", "jobsearch", "run"]
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self.lines: list[str] = []
        self.exit_code: int | None = None
        self.ingested = False

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        """Launch a run; False when one is already in flight."""
        with self._lock:
            if self.running:
                return False
            self.lines, self.exit_code, self.ingested = [], None, False
            self._proc = subprocess.Popen(
                self._cmd, cwd=self.root, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True)
            threading.Thread(target=self._pump, daemon=True).start()
            return True

    def _pump(self) -> None:
        proc = self._proc
        for line in proc.stdout:
            self.lines.append(line.rstrip())
        self.exit_code = proc.wait()

    def snapshot(self, since: int = 0) -> dict:
        """Log lines from `since` on, plus run state — the polling payload."""
        lines = self.lines[since:]
        return {"lines": lines, "next": since + len(lines),
                "running": self.running, "exit_code": self.exit_code}
