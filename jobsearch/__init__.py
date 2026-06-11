"""Daily NYC senior-software-engineer job finder.

Pulls postings straight from company job boards (Greenhouse, Lever, Ashby,
Workday, and FAANG-specific APIs), ranks companies and jobs against a resume
with TF-IDF + K-means, and writes a recency-weighted daily report.
"""

__version__ = "0.1.0"
