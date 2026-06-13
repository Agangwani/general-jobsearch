"""Resume → role profile: target the roles a resume is actually for.

The pipeline used to hard-code "senior software engineer" — the query, the
title_include/title_exclude regexes, and the company set were all SWE. A
Customer Success or Project Management resume therefore came back full of SWE
jobs, because the resume only ever fed *scoring* (re-ranking postings that had
already passed the SWE title filter), never *what* was searched or filtered.

This module closes that gap. It matches the resume to its nearest occupation(s)
in an O*NET-shaped knowledge base (config/occupations.yaml) and turns the
matched entry into a RoleProfile: a search query, generated title_include /
title_exclude patterns, Muse job categories, and the resume's relevant skills.
pipeline.run and company_discovery consume the profile so the whole pipeline
re-targets per resume.

Matching has two backends, both offline:

- **tfidf** (default, no extra dependency): the resume and each occupation's
  text are embedded in a shared TF-IDF space and cosine-matched — the same
  sklearn machinery scoring.py already uses for postings.
- **minilm** (optional, more robust to vocabulary mismatch like "customer
  success" ≈ "client engagement"): sentence-transformers all-MiniLM-L6-v2.
  Falls back to tfidf automatically when the package or model isn't available,
  so nothing breaks offline / in CI.

Everything except the optional MiniLM embedding call is pure and offline-tested.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

# Words that mark a level rather than the role itself — stripped when deriving
# title_include patterns so "Senior Customer Success Manager" matches a profile
# built from the title "Customer Success Manager".
_LEVEL_WORDS = frozenset({
    "senior", "sr", "jr", "junior", "lead", "staff", "principal", "distinguished",
    "associate", "entry", "mid", "level", "i", "ii", "iii", "iv", "1", "2", "3", "4",
})
_BASE_EXCLUDE = ["intern", "internship", "co-?op", "new grad", "university",
                 "campus", "apprentice", "trainee"]
_IC_EXCLUDE = ["manager", "director", "vp", "vice president", "head of",
               "principal", "chief"]
_SENIOR_EXCLUDE = ["junior", "associate", "entry[- ]level", "intern"]

_YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*years?\b", re.I)
_LEADERSHIP_RE = re.compile(
    r"\b(director|vp|vice president|chief|head of|founder|partner|principal)\b", re.I)
_SENIOR_RE = re.compile(r"\b(senior|sr|lead|staff|principal|manager)\b", re.I)


@dataclass
class Occupation:
    name: str
    titles: list[str] = field(default_factory=list)
    query: str = ""
    skills: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    manage: bool = False
    soc: str = ""

    def document(self) -> str:
        """The text matched against the resume. Titles and skills are repeated
        once so they outweigh the single name mention."""
        return " ".join([self.name] + self.titles + self.titles + self.skills + self.skills)


@dataclass
class RoleProfile:
    occupations: list[str]
    query: str
    title_include: list[str]
    title_exclude: list[str]
    skills: list[str]
    categories: list[str]
    seniority: str
    matched_via: str
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def load_occupations(path: Path) -> list[Occupation]:
    raw = yaml.safe_load(path.read_text()) or {}
    occupations = []
    for entry in raw.get("occupations", []):
        occupations.append(Occupation(
            name=entry["name"],
            titles=entry.get("titles", []),
            query=entry.get("query", ""),
            skills=entry.get("skills", []),
            categories=entry.get("categories", []),
            manage=bool(entry.get("manage", False)),
            soc=str(entry.get("soc", "")),
        ))
    return occupations


# --------------------------------------------------------------- seniority ---

def infer_seniority(resume_text: str) -> str:
    """junior / mid / senior / leadership, from level cues and years of
    experience. Drives whether generated title filters keep or drop management
    titles (an IC shouldn't get director roles; a director shouldn't be capped
    at non-management ones)."""
    text = resume_text or ""
    years = max((int(m.group(1)) for m in _YEARS_RE.finditer(text)), default=0)
    head = text[:600]  # title/summary region carries the strongest signal
    if _LEADERSHIP_RE.search(head) or years >= 15:
        return "leadership"
    if _SENIOR_RE.search(head) or years >= 8:
        return "senior"
    if years >= 3:
        return "mid"
    return "junior"


# ----------------------------------------------------------------- matching ---

def _vectorize_match_tfidf(resume_text: str, occupations: list[Occupation]) -> list[float]:
    import numpy as np
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.preprocessing import normalize

    from .scoring import EXTRA_STOP_WORDS

    docs = [occ.document() for occ in occupations]
    vectorizer = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP_WORDS),
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    matrix = normalize(vectorizer.fit_transform(docs))
    resume_vec = normalize(vectorizer.transform([resume_text]))
    return list(np.asarray(matrix @ resume_vec.T.toarray().ravel()).ravel())


@lru_cache(maxsize=1)
def _load_minilm():
    """Import + load the MiniLM model once. Returns None when unavailable
    (package missing, or model can't be fetched offline) — callers fall back
    to TF-IDF."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001 — any failure means "fall back to tfidf"
        return None


def _vectorize_match_minilm(resume_text: str, occupations: list[Occupation]) -> list[float] | None:
    model = _load_minilm()
    if model is None:
        return None
    import numpy as np

    docs = [occ.document() for occ in occupations]
    embeddings = model.encode(docs + [resume_text], normalize_embeddings=True)
    resume_vec = embeddings[-1]
    return [float(np.dot(vec, resume_vec)) for vec in embeddings[:-1]]


def match_occupations(
    resume_text: str, occupations: list[Occupation], backend: str = "auto"
) -> tuple[list[tuple[Occupation, float]], str]:
    """Rank occupations by similarity to the resume. Returns (ranked, backend
    actually used). `backend`: 'tfidf', 'minilm', or 'auto' (minilm when the
    model loads, else tfidf)."""
    used = "tfidf"
    scores = None
    if backend in ("minilm", "auto"):
        scores = _vectorize_match_minilm(resume_text, occupations)
        if scores is not None:
            used = "minilm"
    if scores is None:
        scores = _vectorize_match_tfidf(resume_text, occupations)
    ranked = sorted(zip(occupations, scores), key=lambda pair: -pair[1])
    return ranked, used


# ------------------------------------------------------------ profile build ---

def _deleveled_titles(titles: list[str]) -> list[str]:
    """Title strings with leading/trailing level words removed, for building
    precise include patterns. 'Senior Data Engineer' → 'data engineer'."""
    cores: list[str] = []
    seen: set[str] = set()
    for title in titles:
        tokens = re.findall(r"[a-z0-9&/+]+", title.lower())
        core_tokens = [t for t in tokens if t not in _LEVEL_WORDS]
        core = " ".join(core_tokens).strip()
        if core and core not in seen:
            seen.add(core)
            cores.append(core)
    return cores


def _title_to_pattern(core: str) -> str:
    """A de-leveled title core → a forgiving regex (flexible whitespace,
    optional hyphen between word pairs, '/' and '&' literalised)."""
    words = re.findall(r"[a-z0-9&/+]+", core)
    escaped = [re.escape(w) for w in words]
    return r"\b" + r"[\s/-]+".join(escaped) + r"\b"


def build_title_filters(
    occupations: list[Occupation], seniority: str
) -> tuple[list[str], list[str]]:
    """Generated (title_include, title_exclude). Include = the occupations'
    de-leveled titles. Exclude is seniority-aware: an IC (junior/mid) drops
    management titles; a senior/leadership profile drops junior ones; a
    management occupation never excludes manager/director."""
    cores: list[str] = []
    seen: set[str] = set()
    for occ in occupations:
        for core in _deleveled_titles(occ.titles):
            if core not in seen:
                seen.add(core)
                cores.append(core)
    include = [_title_to_pattern(core) for core in cores]

    exclude = list(_BASE_EXCLUDE)
    is_management = any(occ.manage for occ in occupations)
    if seniority in ("senior", "leadership"):
        exclude += _SENIOR_EXCLUDE
    if seniority in ("junior", "mid") and not is_management:
        exclude += _IC_EXCLUDE
    # Dedupe while preserving order.
    seen_ex: set[str] = set()
    exclude = [e for e in exclude if not (e in seen_ex or seen_ex.add(e))]
    return include, [r"\b(" + e + r")\b" for e in exclude]


def build_profile(
    resume_text: str,
    occupations: list[Occupation],
    backend: str = "auto",
    blend_ratio: float = 0.85,
    max_occupations: int = 2,
) -> RoleProfile:
    """Match the resume and assemble its RoleProfile. The top occupation
    anchors the query; a close runner-up (score ≥ blend_ratio × top) is blended
    in so a resume straddling, say, Customer Success and Project Management
    targets both."""
    ranked, used = match_occupations(resume_text, occupations, backend)
    top_occ, top_score = ranked[0]
    chosen = [top_occ]
    for occ, score in ranked[1:max_occupations]:
        if top_score > 0 and score >= blend_ratio * top_score:
            chosen.append(occ)

    seniority = infer_seniority(resume_text)
    include, exclude = build_title_filters(chosen, seniority)

    skills: list[str] = []
    categories: list[str] = []
    for occ in chosen:
        for skill in occ.skills:
            if skill not in skills:
                skills.append(skill)
        for category in occ.categories:
            if category not in categories:
                categories.append(category)

    return RoleProfile(
        occupations=[occ.name for occ in chosen],
        query=top_occ.query or top_occ.name.lower(),
        title_include=include,
        title_exclude=exclude,
        skills=skills,
        categories=categories,
        seniority=seniority,
        matched_via=used,
        scores={occ.name: round(float(score), 4) for occ, score in ranked[:5]},
    )


def resolve_profile(root: Path, settings: dict, resume_text: str) -> RoleProfile | None:
    """Build the role profile honoring settings: returns None when role
    targeting is off (`search.role_targeting: manual`) or the best match is
    below `search.role_match_min_score` (default 0.02) — in which case callers
    keep the hand-tuned settings.yaml filters."""
    search = settings.get("search", {})
    if search.get("role_targeting", "auto") == "manual":
        return None
    occ_path = root / settings.get("role", {}).get(
        "occupations_file", "config/occupations.yaml")
    if not occ_path.exists():
        return None
    occupations = load_occupations(occ_path)
    if not occupations:
        return None
    backend = search.get("role_match_backend", "auto")
    profile = build_profile(resume_text, occupations, backend=backend)
    min_score = float(search.get("role_match_min_score", 0.02) or 0.0)
    best = max(profile.scores.values(), default=0.0)
    if best < min_score:
        return None
    return profile


def apply_profile(search_settings: dict, profile: RoleProfile) -> dict:
    """A copy of search_settings with the profile's query and generated title
    filters substituted in. Locations and the remote/pay knobs are left
    untouched — the profile decides *what role*, settings decide *where*."""
    return {
        **search_settings,
        "query": profile.query,
        "title_include": profile.title_include,
        "title_exclude": profile.title_exclude,
    }
