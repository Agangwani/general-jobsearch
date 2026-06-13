#!/usr/bin/env python3
"""Distil an O*NET database release into config/occupations.yaml.

config/occupations.yaml ships as a hand-curated seed covering the common role
families. To widen coverage to all ~900 O*NET occupations, download a release
of the O*NET database (text files) from

    https://www.onetcenter.org/database.html#individual-files

and run:

    python tools/build_occupations.py /path/to/db_XX_X_text > config/occupations.yaml

O*NET data is in the public domain (U.S. Department of Labor); attribution is
appreciated. This script reads four tab-delimited files and emits the same
schema role_profile.load_occupations expects (name/soc/titles/query/skills/
categories). The Muse `categories` mapping is coarse (by SOC major group) and
worth hand-tuning afterward — the seed file's categories are more precise.

Kept dependency-light (stdlib + pyyaml) and out of the package so it never runs
in the pipeline; it's an authoring tool you invoke by hand.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import yaml

# O*NET-SOC major group (first 2 digits) → Muse categories. Coarse on purpose.
_MAJOR_GROUP_CATEGORIES = {
    "11": ["Business Operations", "Project and Program Management"],
    "13": ["Business Operations", "Accounting and Finance"],
    "15": ["Software Engineering", "Data and Analytics"],
    "27": ["Design and UX", "Creative and Design"],
    "41": ["Sales", "Account Management"],
    "43": ["Customer Service", "Business Operations"],
}
_TITLES_PER_OCC = 12
_SKILLS_PER_OCC = 14


def _read(path: Path, *columns: str) -> list[dict]:
    with path.open(encoding="latin-1", newline="") as handle:
        return [{c: row[c] for c in columns}
                for row in csv.DictReader(handle, delimiter="\t")]


def build(db_dir: Path) -> dict:
    occ_rows = _read(db_dir / "Occupation Data.txt", "O*NET-SOC Code", "Title")
    titles = defaultdict(list)
    for row in _read(db_dir / "Alternate Titles.txt", "O*NET-SOC Code", "Alternate Title"):
        titles[row["O*NET-SOC Code"]].append(row["Alternate Title"])

    skills = defaultdict(list)
    for fname, col in (("Skills.txt", "Element Name"),
                       ("Technology Skills.txt", "Example")):
        path = db_dir / fname
        if not path.exists():
            continue
        for row in _read(path, "O*NET-SOC Code", col):
            value = row[col].strip().lower()
            if value and value not in skills[row["O*NET-SOC Code"]]:
                skills[row["O*NET-SOC Code"]].append(value)

    occupations = []
    for row in occ_rows:
        code = row["O*NET-SOC Code"]
        name = row["Title"]
        alt = [name] + [t for t in titles.get(code, []) if t.lower() != name.lower()]
        occupations.append({
            "name": name,
            "soc": code,
            "titles": alt[:_TITLES_PER_OCC],
            "query": name.lower(),
            "skills": skills.get(code, [])[:_SKILLS_PER_OCC],
            "categories": _MAJOR_GROUP_CATEGORIES.get(code[:2], ["Business Operations"]),
        })
    return {"occupations": occupations}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = build(Path(argv[1]))
    print("# GENERATED from an O*NET database release by tools/build_occupations.py")
    print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
