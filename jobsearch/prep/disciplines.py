"""Map a resume's matched occupation(s) to the interview-prep *disciplines* that
are relevant to it, and decide which prep tracks to recommend.

The prep curriculum used to be software-engineering only. It now spans many
disciplines (behavioral, case/consulting, finance, product, data, sales,
marketing, design, and a few industry-specific tracks). Each track declares the
disciplines it serves via a ``disciplines`` list; this module turns the role
profile (``occupations``) into a discipline set and intersects the two so the
/prep page can lead with "recommended for your resume".

``GENERAL`` is the universal discipline: the Behavioral Interviews track carries
it and is therefore recommended for *every* resume — behavioral questions are
asked in every industry. The original software tracks remain available to
everyone; they are simply highlighted for software/eng resumes.

Everything here is pure data + functions (no I/O), so it is fully offline-tested.
"""

from __future__ import annotations

GENERAL = "general"

# Occupation display name (config/occupations.yaml) -> prep disciplines.
# Keep every occupation mapped to at least one discipline that owns a track, so
# every resume surfaces a relevant non-behavioral track in addition to Behavioral.
OCCUPATION_DISCIPLINES: dict[str, list[str]] = {
    # ---- Software / engineering ------------------------------------------
    "Software Engineer": ["software"],
    "Frontend Engineer": ["software"],
    "Machine Learning Engineer": ["software", "data"],
    "Data Engineer": ["software", "data"],
    "DevOps / Site Reliability Engineer": ["software"],
    "Security Engineer": ["software"],
    "Cloud / Solutions Architect": ["software"],
    "Engineering Manager": ["software"],
    # ---- Data / analytics ------------------------------------------------
    "Data Scientist": ["data"],
    "Data Analyst": ["data"],
    # ---- Product / program -----------------------------------------------
    "Product Manager": ["product"],
    "Technical Program Manager": ["product"],
    "Project Manager": ["operations"],
    # ---- Design -----------------------------------------------------------
    "Product Designer": ["design"],
    "Architecture / Construction": ["design"],
    # ---- Consulting / strategy / policy ----------------------------------
    "Management Consultant": ["consulting"],
    "Public Policy / Government": ["consulting"],
    # ---- Operations (case + behavioral heavy) ----------------------------
    "Operations Manager": ["operations"],
    "Supply Chain / Logistics": ["operations"],
    "Retail / Merchandising": ["operations"],
    "Hospitality Management": ["operations"],
    "Nonprofit / Social Services": ["operations"],
    # ---- Sales / customer-facing -----------------------------------------
    "Account Executive": ["sales"],
    "Customer Success Manager": ["sales"],
    "Solutions / Sales Engineer": ["sales"],
    # ---- Marketing / content ---------------------------------------------
    "Marketing Manager": ["marketing"],
    "Editorial / Content": ["marketing"],
    # ---- Finance ----------------------------------------------------------
    "Finance / FP&A": ["finance"],
    "Investment Banking / Capital Markets": ["finance"],
    "Accountant / Auditor": ["finance"],
    "Insurance / Underwriting": ["finance"],
    "Real Estate": ["finance"],
    # ---- Healthcare / life sciences --------------------------------------
    "Registered Nurse": ["healthcare"],
    "Healthcare Administrator": ["healthcare"],
    "Clinical Research / Life Sciences": ["healthcare"],
    # ---- Other professional fields ---------------------------------------
    "Attorney / Legal Counsel": ["legal"],
    "Education / Teaching": ["education"],
    "Recruiter / People": ["hr"],
}


def disciplines_for_occupations(occupations: list[str]) -> list[str]:
    """The de-duplicated disciplines for a resume's matched occupation(s),
    always including GENERAL (behavioral prep is universal). Order-stable:
    GENERAL first, then disciplines in occupation order."""
    out: list[str] = [GENERAL]
    for name in occupations or []:
        for disc in OCCUPATION_DISCIPLINES.get(name, []):
            if disc not in out:
                out.append(disc)
    return out


def track_is_relevant(track_disciplines: list[str], resume_disciplines: list[str]) -> bool:
    """A track is relevant when it shares any discipline with the resume. A
    track tagged GENERAL (behavioral) is relevant to everyone. A track with no
    disciplines declared is treated as universally available (not hidden)."""
    if not track_disciplines:
        return True
    if GENERAL in track_disciplines:
        return True
    return bool(set(track_disciplines) & set(resume_disciplines))


def split_tracks(tracks: list[dict], resume_disciplines: list[str] | None):
    """Partition ``tracks`` (each a dict with a 'disciplines' list and a 'slug')
    into (recommended, other) given the resume's disciplines. With no resume
    disciplines (no resume / role targeting off) nothing is singled out and all
    tracks land in ``other`` so the page still shows the full catalog."""
    if not resume_disciplines:
        return [], list(tracks)
    recommended, other = [], []
    for track in tracks:
        if track_is_relevant(track.get("disciplines") or [], resume_disciplines):
            recommended.append(track)
        else:
            other.append(track)
    return recommended, other
