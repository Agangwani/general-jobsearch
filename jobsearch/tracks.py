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

from dataclasses import dataclass, field
from pathlib import Path

MAIN = "main"
STARTUPS = "startups"
TRACKS = (MAIN, STARTUPS)


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


def _subs(values, fallback) -> list[str]:
    return [str(v).lower() for v in (values or fallback or [])]


def build_track(root: Path, settings: dict, name: str = MAIN) -> Track:
    """Resolve the paths and discovery config for a track from settings."""
    search = settings.get("search", {}) or {}
    if name == STARTUPS:
        cfg = settings.get("startups", {}) or {}
        reports = root / cfg.get("reports_dir", "reports/startups")
        return Track(
            name=STARTUPS,
            is_startup=True,
            reports_dir=reports,
            state_file=root / cfg.get("state_file", "data/seen_jobs.startups.tsv"),
            corpus_dir=root / cfg.get("corpus_dir", "data/corpus-startups"),
            registry_file=root / cfg.get("output_file", "data/companies.startups.yaml"),
            curated_file=root / "config" / "startups.yaml",
            meta_file=root / cfg.get("meta_file", "data/startup_meta.json"),
            discovery=cfg,
            locations=_subs(cfg.get("locations"), search.get("locations")),
            location=cfg.get("location", "New York, NY"),
            exclude=cfg.get("exclude_companies") or [],
        )
    discovery = settings.get("discovery", {}) or {}
    output = settings.get("output", {}) or {}
    return Track(
        name=MAIN,
        is_startup=False,
        reports_dir=root / output.get("reports_dir", "reports"),
        state_file=root / output.get("state_file", "data/seen_jobs.tsv"),
        corpus_dir=root / output.get("corpus_dir", "data/corpus"),
        registry_file=root / discovery.get("output_file", "data/companies.discovered.yaml"),
        curated_file=root / "config" / "companies.yaml",
        meta_file=None,
        discovery=discovery,
        locations=_subs(search.get("locations"), []),
        location=discovery.get("location", "New York, NY"),
        exclude=discovery.get("exclude_companies") or [],
    )
