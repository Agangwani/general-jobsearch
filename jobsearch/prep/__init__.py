"""Software-interview prep content.

The four source documents (Cracking the Coding Interview 6e; Designing
Data-Intensive Applications; System Design Interview Vol. 1 by Alex Xu;
Grokking the Modern System Design Interview) are distilled into three
"tracks" of modules and lessons. Each lesson carries its source citation
(e.g., ``CtCI p. 41``) so a user can verify or read deeper.

``ALL_TRACKS`` is the canonical content. ``seed.seed_into_db(conn)`` writes
it into the prep_* tables — idempotent via a content hash, so progress
isn't wiped when content evolves.
"""

from .coding import TRACK_CODING
from .system_design import TRACK_SYSTEM_DESIGN
from .distributed_systems import TRACK_DISTRIBUTED

ALL_TRACKS = [TRACK_CODING, TRACK_SYSTEM_DESIGN, TRACK_DISTRIBUTED]

__all__ = ["ALL_TRACKS", "TRACK_CODING", "TRACK_SYSTEM_DESIGN", "TRACK_DISTRIBUTED"]
