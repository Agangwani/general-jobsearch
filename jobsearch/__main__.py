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

    args = parser.parse_args(argv)
    if args.command == "run":
        return pipeline.run(args.root)
    if args.command == "verify":
        return pipeline.verify(args.root)
    return 2


if __name__ == "__main__":
    sys.exit(main())
