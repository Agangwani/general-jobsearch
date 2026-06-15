"""Referral discovery: find people who can refer you to a given job.

P1 scope: LinkedIn-driven candidate discovery via Playwright, ranked by job
fit and personal fit (TF-IDF over the resume and job description). Browser
runs headed against a persistent profile under data/browser_profile/linkedin/
so LinkedIn login is one-time. Auto-DM and Claude-generated messages land in
later phases (see docs/design-referrals.md when added).
"""
