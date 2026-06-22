"""Interview-prep content across disciplines.

The original three software tracks (Cracking the Coding Interview 6e; Designing
Data-Intensive Applications; System Design Interview Vol. 1 by Alex Xu; Grokking
the Modern System Design Interview) are joined by discipline tracks for the rest
of the job market: a universal **Behavioral** track plus **Case** (consulting),
**Finance**, **Product Management**, **Data & Analytics**, **Sales/CS**,
**Marketing**, **Design**, and **Industry-Specific** (healthcare/legal/education/
HR) tracks. Each lesson carries its source citation so a user can read deeper.

Each track declares a ``disciplines`` list; ``prep/disciplines.py`` maps a
resume's matched occupation(s) to those disciplines so the /prep page can lead
with "recommended for your resume". The Behavioral track is tagged ``general``
and is recommended for everyone — behavioral questions are asked in every field.

``ALL_TRACKS`` is the canonical content. ``seed.seed_into_db(conn)`` writes it
into the prep_* tables — idempotent via a content hash, so progress isn't wiped
when content evolves.
"""

from .behavioral import TRACK_BEHAVIORAL
from .case_interview import TRACK_CASE
from .coding import TRACK_CODING
from .data_analytics import TRACK_DATA
from .design import TRACK_DESIGN
from .distributed_systems import TRACK_DISTRIBUTED
from .finance import TRACK_FINANCE
from .industry_interviews import TRACK_INDUSTRY
from .marketing import TRACK_MARKETING
from .product_management import TRACK_PM
from .sales_cs import TRACK_SALES
from .system_design import TRACK_SYSTEM_DESIGN

# Order matters: it's the default display order on /prep. Behavioral leads (it's
# universal), then the software tracks (the original curriculum), then the other
# discipline tracks.
ALL_TRACKS = [
    TRACK_BEHAVIORAL,
    TRACK_CODING,
    TRACK_SYSTEM_DESIGN,
    TRACK_DISTRIBUTED,
    TRACK_CASE,
    TRACK_FINANCE,
    TRACK_PM,
    TRACK_DATA,
    TRACK_SALES,
    TRACK_MARKETING,
    TRACK_DESIGN,
    TRACK_INDUSTRY,
]

__all__ = [
    "ALL_TRACKS",
    "TRACK_BEHAVIORAL",
    "TRACK_CODING",
    "TRACK_SYSTEM_DESIGN",
    "TRACK_DISTRIBUTED",
    "TRACK_CASE",
    "TRACK_FINANCE",
    "TRACK_PM",
    "TRACK_DATA",
    "TRACK_SALES",
    "TRACK_MARKETING",
    "TRACK_DESIGN",
    "TRACK_INDUSTRY",
]
