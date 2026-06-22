"""Boot the jobsearch web app in isolation so a run can't touch real data.

Each run gets a throwaway project root (temp dir) with a copy of config/, a
data/ seeded from the persona, and a fresh SQLite DB pre-loaded with fixture
jobs. The app is launched exactly as a user would (`python -m jobsearch ui
--root <tmp>`), as a subprocess, with stdout+stderr tee'd to a log file — that
log is where uncaught request-handler exceptions land, which is how the harness
catches *server-side* errors the browser alone can't see.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from . import fixtures
from .persona import Persona

# Marks in the captured server log that signal a real failure. uvicorn logs
# unhandled endpoint exceptions at ERROR with a traceback even at warning level.
_SERVER_ERROR_MARKERS = ("Traceback (most recent call last)",
                         "ERROR:", " - \"", "Internal Server Error",
                         "Exception in ASGI application")


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


class AppServer:
    """Context manager: an isolated, seeded, running instance of the UI.

    Attributes after __enter__:
      base_url       e.g. http://127.0.0.1:54123
      root           the temp project root
      job_ids        {pipeline_key: db_id} for the seeded jobs
      log_path       captured server stdout+stderr
    """

    def __init__(self, repo_root: Path, persona: Persona | None = None, *,
                 host: str = "127.0.0.1", seed: bool = True,
                 keep: bool = False):
        self.repo_root = Path(repo_root).resolve()
        self.persona = persona or Persona.load(self.repo_root)
        self.host = host
        self.seed = seed
        self.keep = keep
        self.port = _free_port(host)
        self.base_url = f"http://{host}:{self.port}"
        self.root: Path = Path()
        self.job_ids: dict[str, int] = {}
        self.log_path: Path = Path()
        self._proc: subprocess.Popen | None = None
        self._log_fh = None
        self._log_cursor = 0

    # ---------------------------------------------------------------- lifecycle
    def __enter__(self) -> "AppServer":
        self.root = Path(tempfile.mkdtemp(prefix="uiqa-"))
        self._scaffold()
        if self.seed:
            self.job_ids = fixtures.seed(self.root, self.root / "data" / "jobsearch.db")
        self._launch()
        self._await_health()
        return self

    def __exit__(self, *exc) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._log_fh:
            self._log_fh.close()
        if not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------------ scaffold
    def _scaffold(self) -> None:
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / "reports").mkdir(parents=True, exist_ok=True)
        cfg_dst = self.root / "config"
        cfg_dst.mkdir(exist_ok=True)
        for yml in (self.repo_root / "config").glob("*.yaml"):
            shutil.copy(yml, cfg_dst / yml.name)
        # Persona resume + a sample copy so role-targeting and profile seeding run.
        (self.root / "data" / "resume.txt").write_text(self.persona.resume_text)
        sample = self.repo_root / "data" / "sample_resume.txt"
        if sample.exists():
            shutil.copy(sample, self.root / "data" / "sample_resume.txt")

    def _launch(self) -> None:
        self.log_path = self.root / "server.log"
        self._log_fh = open(self.log_path, "w+b")
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        # So the app's own integrated apply-browser can launch if an agent ever
        # exercises it; harmless otherwise.
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH",
                       str(_default_browsers_path()) if _default_browsers_path() else "0")
        self._proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "jobsearch", "ui",
             "--host", self.host, "--port", str(self.port)],
            cwd=self.repo_root, env=env,
            stdout=self._log_fh, stderr=subprocess.STDOUT, text=False)

    def _await_health(self, timeout: float = 40.0) -> None:
        deadline = time.time() + timeout
        last_err = ""
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError(
                    f"server exited early (code {self._proc.returncode}):\n"
                    + self._tail_log())
            try:
                with urllib.request.urlopen(self.base_url + "/", timeout=3) as r:
                    if r.status == 200:
                        return
            except Exception as exc:  # noqa: BLE001 — still starting up
                last_err = str(exc)
            time.sleep(0.4)
        raise RuntimeError(f"server did not become healthy in {timeout}s "
                           f"(last error: {last_err})\n" + self._tail_log())

    # --------------------------------------------------------------- server log
    def server_errors_since(self, cursor: int | None = None) -> tuple[list[str], int]:
        """New server-log lines that look like errors, plus the new cursor.
        Lets the scenario runner attribute server-side failures to the step that
        triggered them."""
        if self._log_fh is None:
            return [], 0
        self._log_fh.flush()
        start = self._log_cursor if cursor is None else cursor
        with open(self.log_path, "r", errors="replace") as fh:
            fh.seek(start)
            chunk = fh.read()
            new_cursor = fh.tell()
        if cursor is None:
            self._log_cursor = new_cursor
        hits = [ln for ln in chunk.splitlines()
                if any(m in ln for m in _SERVER_ERROR_MARKERS)
                # 2xx/3xx access lines aren't errors; only flag 4xx/5xx requests.
                and not _is_ok_access_line(ln)]
        return hits, new_cursor

    def _tail_log(self, n: int = 40) -> str:
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-n:])
        except OSError:
            return "(no server log)"


def _is_ok_access_line(line: str) -> bool:
    """uvicorn access lines look like `... "GET / HTTP/1.1" 200`. Treat 2xx/3xx
    as fine; 4xx/5xx are surfaced. The ` - "` marker would otherwise match all."""
    if '" ' not in line:
        return False
    tail = line.rsplit('" ', 1)[-1].strip()
    code = tail.split()[0] if tail else ""
    return code[:1] in {"2", "3"}


def _default_browsers_path() -> Path | None:
    """The repo's environments ship a pre-installed Playwright browser here; use
    it when the user hasn't set PLAYWRIGHT_BROWSERS_PATH so the harness works
    without a (often network-blocked) `playwright install`."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    for cand in (Path("/opt/pw-browsers"), Path.home() / ".cache" / "ms-playwright"):
        if cand.exists():
            return cand
    return None
