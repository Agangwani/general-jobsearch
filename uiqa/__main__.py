"""Command-line surface the agents (and you) drive.

  python -m uiqa explore                      deterministic Stage-1 crawl + battery
  python -m uiqa index --path /resume         dump a page's action index (JSON)
  python -m uiqa run-scenario journey.json     run one journey, print the result
  python -m uiqa replay --scenario j.json      re-run a journey; print reproduced y/n
  python -m uiqa replay --findings f.json --id ID
  python -m uiqa serve [--port N]              boot the seeded app and hold it open

Every command prints JSON (except serve) so agents can act on the result.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cmd_explore(args) -> int:
    from .explore import explore
    summary = explore(args.root, persona_name=args.persona, run_id=args.run_id,
                      max_pages=args.max_pages, headless=not args.headed)
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_index(args) -> int:
    from .appserver import AppServer
    from .browser import BrowserSession
    from .actions import index_actions
    from .persona import Persona
    persona = Persona.load(args.root, args.persona)
    with AppServer(args.root, persona) as server, \
            BrowserSession(headless=not args.headed, base_url=server.base_url) as browser:
        # Substitute a real seeded id for {id} so deep routes resolve.
        path = args.path
        if "{id}" in path:
            path = path.replace("{id}", str(next(iter(server.job_ids.values()), 1)))
        status = browser.goto(path)
        out = {"path": path, "status": status, "title": browser.title(),
               "actions": index_actions(browser.page),
               "job_ids": server.job_ids}
    print(json.dumps(out, indent=2))
    return 0


def _cmd_run_scenario(args) -> int:
    from .scenario import run_scenario_file
    out_dir = Path(args.out) if args.out else \
        Path(tempfile.mkdtemp(prefix="uiqa-scn-"))
    result = run_scenario_file(args.root, Path(args.scenario), out_dir,
                               persona_name=args.persona, headless=not args.headed)
    result["out_dir"] = str(out_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def _cmd_replay(args) -> int:
    from .scenario import run_scenario_file
    if args.scenario:
        scenario = json.loads(Path(args.scenario).read_text())
    else:
        from . import findings as F
        items = json.loads(Path(args.findings).read_text())
        match = next((f for f in items if f.get("id") == args.id), None)
        if not match or not match.get("repro"):
            print(json.dumps({"error": f"no repro for finding {args.id}"}))
            return 2
        scenario = match["repro"]
    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="uiqa-replay-"))
    scn_file = out_dir / "repro.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    scn_file.write_text(json.dumps(scenario))
    result = run_scenario_file(args.root, scn_file, out_dir,
                               persona_name=args.persona, headless=not args.headed)
    verdict = {"reproduced": result["problem_count"] > 0,
               "problem_count": result["problem_count"],
               "out_dir": str(out_dir),
               "problems": [p for s in result["steps"] for p in s["problems"]]}
    print(json.dumps(verdict, indent=2))
    return 0


def _cmd_consolidate(args) -> int:
    """Merge findings.jsonl + incoming/*.json → findings.json and refresh
    summary.md. Run after the explorer sub-agents finish, and again after the
    validator writes validation.json."""
    from .report import RunDir
    run_dir = Path(args.run_dir).resolve()
    rundir = RunDir(run_dir.parent.parent.parent, run_dir.name)
    merged = rundir.consolidate()
    action_index = json.loads(rundir.action_index.read_text()) \
        if rundir.action_index.exists() else {}
    verdicts = json.loads(rundir.validation_json.read_text()) \
        if rundir.validation_json.exists() else []
    if isinstance(verdicts, dict):  # tolerate {"verdicts": [...]} shape
        verdicts = verdicts.get("verdicts", [])
    rundir.write_summary(action_index=action_index, findings=merged, verdicts=verdicts)
    confirmed = [f for f in merged
                 if any(v.get("finding_id") == f["id"] and v.get("verdict") == "confirmed"
                        for v in verdicts)]
    print(json.dumps({"run_dir": str(rundir.base), "findings": len(merged),
                      "high": sum(1 for f in merged if f["severity"] == "high"),
                      "verdicts": len(verdicts), "confirmed": len(confirmed),
                      "confirmed_ids": [f["id"] for f in confirmed]}, indent=2))
    return 0


def _cmd_serve(args) -> int:
    import time
    from .appserver import AppServer
    from .persona import Persona
    persona = Persona.load(args.root, args.persona)
    with AppServer(args.root, persona, keep=True) as server:
        print(json.dumps({"base_url": server.base_url, "root": str(server.root),
                          "job_ids": server.job_ids}, indent=2))
        print("serving — Ctrl-C to stop", file=sys.stderr)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="uiqa", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=REPO_ROOT,
                   help="repo root containing config/, data/, webapp/ (default: this repo)")
    p.add_argument("--persona", default="sample", help="persona name (default: sample)")
    p.add_argument("--headed", action="store_true", help="run Chromium headed (debug)")
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("explore", help="deterministic Stage-1 crawl + battery")
    e.add_argument("--run-id", default=None)
    e.add_argument("--max-pages", type=int, default=60)
    e.set_defaults(func=_cmd_explore)

    i = sub.add_parser("index", help="dump a page's action index")
    i.add_argument("--path", default="/")
    i.set_defaults(func=_cmd_index)

    r = sub.add_parser("run-scenario", help="run one scenario file")
    r.add_argument("scenario")
    r.add_argument("--out", default="")
    r.set_defaults(func=_cmd_run_scenario)

    rp = sub.add_parser("replay", help="re-run a scenario / finding repro")
    rp.add_argument("--scenario", default="")
    rp.add_argument("--findings", default="")
    rp.add_argument("--id", default="")
    rp.add_argument("--out", default="")
    rp.set_defaults(func=_cmd_replay)

    c = sub.add_parser("consolidate", help="merge findings + refresh summary")
    c.add_argument("--run-dir", required=True, help="reports/uiqa/<run-id> directory")
    c.set_defaults(func=_cmd_consolidate)

    s = sub.add_parser("serve", help="boot the seeded app and hold it open")
    s.set_defaults(func=_cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
