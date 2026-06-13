from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jobsearch",
        description="Daily NYC senior-SWE job finder: fetch company boards, "
        "rank by resume fit, prioritize recent postings.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root containing config/, data/, reports/ (default: repo root)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Fetch, rank, and write the daily report")
    sub.add_parser("verify", help="Check that every configured job board is reachable")
    disc = sub.add_parser("discover", help="Auto-discover a company's ATS board slug")
    disc.add_argument("company", help="Company name (quoted if multi-word)")
    disc.add_argument("--url", default="", help="Careers page URL (default: from companies.yaml)")
    dcomp = sub.add_parser(
        "discover-companies",
        help="Mine generalized job boards for companies matching your resume "
        "and generate a registry of their ATS boards",
    )
    dcomp.add_argument("--limit", type=int, default=0,
                       help="Max companies to add (default: discovery.max_companies)")
    dcomp.add_argument("--dry-run", action="store_true",
                       help="Print the generated registry instead of writing it")
    sub.add_parser("ingest", help="Pull reports/latest.json into the application database")
    ui = sub.add_parser("ui", help="Start the local application-tracking web UI")
    ui.add_argument("--port", type=int, default=8484)
    ui.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args(argv)
    if args.command == "run":
        return pipeline.run(args.root)
    if args.command == "verify":
        return pipeline.verify(args.root)
    if args.command == "discover":
        from .discover import discover
        return discover(args.root, args.company, careers_url=args.url)
    if args.command == "discover-companies":
        from .company_discovery import discover_companies
        return discover_companies(args.root, limit=args.limit, dry_run=args.dry_run)
    if args.command == "ingest":
        from webapp import db as webdb
        from webapp.ingest import ingest_latest
        conn = webdb.connect(args.root / "data" / "jobsearch.db")
        ingest_latest(args.root, conn)
        return 0
    if args.command == "ui":
        import uvicorn
        from webapp.app import create_app
        app = create_app(args.root)
        print(f"jobsearch UI → http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
