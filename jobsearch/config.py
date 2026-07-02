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


def load_registry(root: Path, settings: dict, track=None) -> tuple[list[Company], list[dict]]:
    """The full company registry for a track: its curated seed plus the
    generated registry, deduped by normalized name. Curated entries win
    conflicts, and the track's exclude list is enforced here too — an excluded
    company can never re-enter through a stale generated file.

    `track` defaults to the main track (curated `config/companies.yaml` +
    generated `data/companies.discovered.yaml`); the startups track reads the
    optional `config/startups.yaml` seed + `data/companies.startups.yaml`."""
    from .tracks import build_track

    if track is None:
        track = build_track(root, settings, "main")

    if track.curated_file and track.curated_file.exists():
        companies, manual = load_companies(track.curated_file)
    else:
        companies, manual = [], []

    known = {normalize_company_name(c.name) for c in companies}
    known |= {normalize_company_name(str(entry.get("name", ""))) for entry in manual}
    exclude = {normalize_company_name(x) for x in track.exclude}

    if not track.registry_file.exists():
        return companies, manual

    extra_companies, extra_manual = load_companies(track.registry_file)
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


def registry_entries(root: Path, settings: dict, track=None) -> list[dict]:
    """The track's live registry as dicts tagged with source ('curated' /
    'discovered') and discovered_via — everything needed to mirror the registry
    into the companies DB table (webapp/db.py). Applies the same precedence as
    load_registry: curated entries win, the track's exclude list gates only the
    generated registry (a curated company is never excluded), and a name already
    seen (including curated manual-check names) is not re-added. Only fetchable
    companies are returned — manual_check entries are leads to resolve by hand,
    not companies the pipeline searches."""
    from .tracks import build_track

    if track is None:
        track = build_track(root, settings, "main")

    exclude = {normalize_company_name(x) for x in track.exclude}
    known: set[str] = set()
    entries: list[dict] = []

    def add(raw: dict, source: str, *, enforce_exclude: bool) -> None:
        key = normalize_company_name(str(raw.get("name", "")))
        if not key or key in known:
            return
        # Mirror load_registry exactly: exclude gates only the generated
        # registry, never the curated seed (curated wins).
        if enforce_exclude and key in exclude:
            return
        known.add(key)
        tags = raw.get("tags", [])
        if isinstance(tags, str):          # tolerate a scalar `tags: discovered`
            tags = [tags] if tags else []
        elif not isinstance(tags, list):
            tags = list(tags or [])
        params = {k: v for k, v in raw.items() if k not in RESERVED_KEYS}
        entries.append({
            "name": raw["name"],
            "ats": raw.get("ats", ""),
            "tags": tags,
            "careers_url": raw.get("careers_url", ""),
            "enabled": raw.get("enabled", True),
            "params": params,
            "source": source,
            "discovered_via": raw.get("discovered_via", ""),
        })

    if track.curated_file and track.curated_file.exists():
        raw = yaml.safe_load(track.curated_file.read_text()) or {}
        for entry in raw.get("companies", []):
            add(entry, "curated", enforce_exclude=False)   # curated is never excluded
        # Curated manual-check names block a generated company of the same name,
        # exactly as load_registry seeds them into `known`.
        for entry in raw.get("manual_check", []):
            key = normalize_company_name(str(entry.get("name", "")))
            if key:
                known.add(key)

    if track.registry_file.exists():
        raw = yaml.safe_load(track.registry_file.read_text()) or {}
        for entry in raw.get("companies", []):
            add(entry, "discovered", enforce_exclude=True)

    return entries


def load_settings(path: Path) -> dict:
    # Tolerate a missing file: callers like ingest run against a bare data dir
    # and only need the defaults below.
    settings = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    settings.setdefault("resume", "data/resume.txt")
    settings.setdefault("search", {})
    settings.setdefault("ranking", {})
    settings.setdefault("fetch", {})
    settings.setdefault("output", {})
    settings.setdefault("discovery", {})
    settings.setdefault("startups", {})
    settings.setdefault("role", {})
    return settings
