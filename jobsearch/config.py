from __future__ import annotations

from pathlib import Path

import yaml

from .models import Company

RESERVED_KEYS = {"name", "ats", "tags", "careers_url", "enabled"}


def load_companies(path: Path) -> tuple[list[Company], list[dict]]:
    """Return (companies, manual_check_entries) from companies.yaml."""
    raw = yaml.safe_load(path.read_text())
    companies = []
    for entry in raw.get("companies", []):
        params = {k: v for k, v in entry.items() if k not in RESERVED_KEYS}
        companies.append(
            Company(
                name=entry["name"],
                ats=entry["ats"],
                tags=entry.get("tags", []),
                careers_url=entry.get("careers_url", ""),
                enabled=entry.get("enabled", True),
                params=params,
            )
        )
    return companies, raw.get("manual_check", [])


def load_settings(path: Path) -> dict:
    settings = yaml.safe_load(path.read_text()) or {}
    settings.setdefault("resume", "data/resume.txt")
    settings.setdefault("search", {})
    settings.setdefault("ranking", {})
    settings.setdefault("fetch", {})
    settings.setdefault("output", {})
    return settings
