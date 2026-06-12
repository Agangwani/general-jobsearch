"""Email module scaffold (Gmail first).

The end state (docs/design-frontend.md): connect a Gmail account read-only,
ingest application confirmations and all subsequent company communications,
link each message to its application/job, and keep everything append-only in
email_messages so the full conversation history per company is searchable
locally.

This scaffold ships the interface, the message→application matcher, and the
classifier — everything except the OAuth flow itself, which needs a Google
Cloud OAuth client the user must create (no credentials in the repo, ever).
The UI shows the connect instructions until an account is connected.
"""

from __future__ import annotations

import re
import sqlite3

from . import db

SETUP_INSTRUCTIONS = """\
To connect Gmail (read-only):
1. Create a Google Cloud project and enable the Gmail API.
2. Create an OAuth client ID (Desktop app) and download credentials.json
   into data/ (gitignored — never commit it).
3. pip install google-api-python-client google-auth-oauthlib
4. Restart the app and click Connect — the OAuth consent flow will open in
   your browser; the token is stored locally in data/.
Scope used: gmail.readonly. The app never sends mail or modifies your inbox.\
"""

CLASSIFIERS = [
    ("confirmation", re.compile(
        r"(application (was |has been )?(received|submitted)"
        r"|thank you for applying|we('ve| have) received your application)", re.I)),
    ("interview", re.compile(
        r"(schedule|availability|interview|phone screen|next (steps|round)|recruiter call)", re.I)),
    ("rejection", re.compile(
        r"(not (be )?moving forward|other candidates|unfortunately"
        r"|decided to pursue|position has been filled)", re.I)),
    ("offer", re.compile(r"(offer letter|pleased to offer|congratulations)", re.I)),
]


def classify(subject: str, body: str) -> str:
    text = f"{subject}\n{body}"[:5000]
    for label, pattern in CLASSIFIERS:
        if pattern.search(text):
            return label
    return "other"


def _company_tokens(company: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", company) if len(t) >= 3]


def match_application(conn: sqlite3.Connection, from_addr: str, subject: str, body: str):
    """Best-effort link of an inbound message to an application: the sender's
    domain or the subject/body must mention the company of an application
    that exists. Returns (application_id, job_id) or (None, None)."""
    candidates = conn.execute(
        """SELECT a.id AS application_id, j.id AS job_id, j.company
           FROM applications a JOIN jobs j ON j.id = a.job_id
           WHERE a.status != 'not_applied'"""
    ).fetchall()
    haystack = f"{from_addr}\n{subject}\n{body[:2000]}".lower()
    best = None
    for row in candidates:
        tokens = _company_tokens(row["company"])
        if tokens and all(t in haystack for t in tokens):
            best = row
            break
        if tokens and any(f"@{t}" in from_addr.lower() or f".{t}." in from_addr.lower()
                          for t in tokens):
            best = best or row
    if best:
        return best["application_id"], best["job_id"]
    return None, None


def store_message(conn: sqlite3.Connection, message: dict) -> str:
    """Append a message (idempotent on provider message_id). Auto-links and
    classifies; a 'confirmation' match advances the application to confirmed."""
    existing = conn.execute(
        "SELECT id FROM email_messages WHERE message_id = ?", (message.get("message_id"),)
    ).fetchone()
    if existing:
        return "duplicate"

    classification = classify(message.get("subject", ""), message.get("body", ""))
    app_id, job_id = match_application(
        conn, message.get("from_addr", ""), message.get("subject", ""), message.get("body", ""))
    conn.execute(
        """INSERT INTO email_messages
           (account_id, application_id, job_id, message_id, thread_id, direction,
            from_addr, to_addr, subject, snippet, body, sent_at, ingested_at, classification)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (message.get("account_id"), app_id, job_id, message.get("message_id"),
         message.get("thread_id"), message.get("direction", "inbound"),
         message.get("from_addr", ""), message.get("to_addr", ""),
         message.get("subject", ""), message.get("snippet", ""),
         message.get("body", ""), message.get("sent_at"), db.utcnow(), classification),
    )
    if app_id and classification == "confirmation":
        current = conn.execute(
            "SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
        if current and current["status"] in ("in_progress", "applied"):
            db.set_application_status(conn, app_id, "confirmed",
                                      detail=f"email confirmation: {message.get('subject','')[:120]}",
                                      via="email")
    conn.commit()
    return classification


def is_connected(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM email_accounts WHERE status = 'connected' LIMIT 1").fetchone()
    return row is not None
