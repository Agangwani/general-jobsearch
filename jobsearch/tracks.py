"""Pipeline tracks: the *main* job search and the parallel *startups* search.

The two pipelines are identical machinery (fetch boards → filter → TF-IDF +
K-means fit → report → fit map) pointed at different company universes and
writing to different files, so instead of forking `pipeline.run` and
`company_discovery` we parameterize them with a small `Track` record.

- **main** — the curated FAANG/top-50 registry merged with the resume-discovered
  registry; writes `reports/`, `data/seen_jobs.tsv`. Exactly today's behavior.
- **startups** — the startup registry built by `discover-startups` (Y Combinator
  directory + HN + The Muse, ranked against the resume); writes
  `reports/startups/`, `data/seen_jobs.startups.tsv`, and the metadata sidecar
  `data/startup_meta.json`. Targets `startups.location` (defaults to the main
  search location) so it can chase a different city than the main run.

Everything else — role targeting, ranking knobs, scoring — is shared, so a
startup run scores the same way the main run does and the Fit map "just works"
for both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MAIN = "main"
STARTUPS = "startups"
TRACKS = (MAIN, STARTUPS)
LOCAL_USER = "local"


@dataclass
class Track:
    name: str
    is_startup: bool
    reports_dir: Path
    state_file: Path
    corpus_dir: Path             # per-track corpus snapshots (descriptions for ingest)
    registry_file: Path          # generated registry this track reads/writes
    curated_file: Path | None    # curated seed merged under the generated one
    meta_file: Path | None       # startup metadata sidecar (startups only)
    discovery: dict = field(default_factory=dict)  # the settings block to mine with
    locations: list[str] = field(default_factory=list)  # client-side location subs
    location: str = ""           # canonical location sent to aggregator APIs
    exclude: list[str] = field(default_factory=list)
    user_id: str = LOCAL_USER    # owner these generated files/reports belong to


def _subs(values, fallback) -> list[str]:
    return [str(v).lower() for v in (values or fallback or [])]


def _scope(rel: str, user_id: str) -> str:
    """Namespace a generated/state path under a per-user segment for hosted
    multi-user runs, so two users' registries/reports/seen-state never collide.
    The local (single-user) owner keeps the original flat paths — byte-for-byte
    unchanged. e.g. 'data/seen_jobs.tsv' → 'data/users/<uid>/seen_jobs.tsv'."""
    if not user_id or user_id == LOCAL_USER:
        return rel
    # Sanitize: user_id lands in a filesystem path, so strip anything that could
    # traverse out of the per-user dir (real Supabase UUIDs are unaffected). When
    # sanitizing actually changes the id, append a short hash of the raw id so
    # two distinct ids that sanitize to the same string don't share a directory.
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)
    if safe != user_id:
        import hashlib
        safe = f"{safe}-{hashlib.sha1(user_id.encode()).hexdigest()[:8]}"
    head, _, tail = rel.partition("/")
    return f"{head}/users/{safe}/{tail}".rstrip("/")


def build_track(root: Path, settings: dict, name: str = MAIN,
                user_id: str = LOCAL_USER) -> Track:
    """Resolve the paths and discovery config for a track from settings. Curated
    seed files (config/companies.yaml, config/startups.yaml) are shared across
    users; only the generated registry, reports, seen-state and corpus are
    namespaced per user."""
    search = settings.get("search", {}) or {}

    def scoped(rel: str) -> Path:
        return root / _scope(rel, user_id)

    if name == STARTUPS:
        cfg = settings.get("startups", {}) or {}
        return Track(
            name=STARTUPS,
            is_startup=True,
            reports_dir=scoped(cfg.get("reports_dir", "reports/startups")),
            state_file=scoped(cfg.get("state_file", "data/seen_jobs.startups.tsv")),
            corpus_dir=scoped(cfg.get("corpus_dir", "data/corpus-startups")),
            registry_file=scoped(cfg.get("output_file", "data/companies.startups.yaml")),
            curated_file=root / "config" / "startups.yaml",
            meta_file=scoped(cfg.get("meta_file", "data/startup_meta.json")),
            discovery=cfg,
            locations=_subs(cfg.get("locations"), search.get("locations")),
            location=cfg.get("location", "New York, NY"),
            exclude=cfg.get("exclude_companies") or [],
            user_id=user_id,
        )
    discovery = settings.get("discovery", {}) or {}
    output = settings.get("output", {}) or {}
    return Track(
        name=MAIN,
        is_startup=False,
        reports_dir=scoped(output.get("reports_dir", "reports")),
        state_file=scoped(output.get("state_file", "data/seen_jobs.tsv")),
        corpus_dir=scoped(output.get("corpus_dir", "data/corpus")),
        registry_file=scoped(discovery.get("output_file", "data/companies.discovered.yaml")),
        curated_file=root / "config" / "companies.yaml",
        meta_file=None,
        discovery=discovery,
        locations=_subs(search.get("locations"), []),
        location=discovery.get("location", "New York, NY"),
        exclude=discovery.get("exclude_companies") or [],
        user_id=user_id,
    )
