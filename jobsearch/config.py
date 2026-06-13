from __future__ import annotations

from pathlib import Path

import yaml

from .models import Company
from .utils import normalize_company_name

# discovered_via is audit metadata on generated entries, not a fetcher param.
RESERVED_KEYS = {"name", "ats", "tags", "careers_url", "enabled", "discovered_via"}


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


def load_registry(root: Path, settings: dict) -> tuple[list[Company], list[dict]]:
    """The full company registry: curated companies.yaml plus the generated
    discovered registry (discover-companies), deduped by normalized name.
    Curated entries win conflicts, and `discovery.exclude_companies` is
    enforced here too — an excluded company can never re-enter through a
    stale generated file."""
    companies, manual = load_companies(root / "config" / "companies.yaml")
    discovery = settings.get("discovery", {}) or {}
    path = root / discovery.get("output_file", "data/companies.discovered.yaml")
    if not path.exists():
        return companies, manual

    known = {normalize_company_name(c.name) for c in companies}
    known |= {normalize_company_name(str(entry.get("name", ""))) for entry in manual}
    exclude = {normalize_company_name(x)
               for x in discovery.get("exclude_companies") or []}
    extra_companies, extra_manual = load_companies(path)
    for company in extra_companies:
        key = normalize_company_name(company.name)
        if not key or key in known or key in exclude:
            continue
        known.add(key)
        companies.append(company)
    for entry in extra_manual:
        key = normalize_company_name(str(entry.get("name", "")))
        if not key or key in known or key in exclude:
            continue
        known.add(key)
        manual.append(entry)
    return companies, manual


def load_settings(path: Path) -> dict:
    settings = yaml.safe_load(path.read_text()) or {}
    settings.setdefault("resume", "data/resume.txt")
    settings.setdefault("search", {})
    settings.setdefault("ranking", {})
    settings.setdefault("fetch", {})
    settings.setdefault("output", {})
    settings.setdefault("discovery", {})
    settings.setdefault("role", {})
    return settings
