"""Gmail connection: OAuth (loopback redirect to the running UI) + sync.

No Google SDK — the OAuth token exchange and the Gmail REST API are a few
plain `requests` calls, which keeps the dependency list unchanged. Setup:

1. Google Cloud console → create a project, enable the Gmail API.
2. Create an OAuth client ID of type **Desktop app** and download the JSON
   as `data/credentials.json` (gitignored — never committed).
3. Click **Connect Gmail** on /emails. The consent screen opens; the token
   lands in `data/token.json` (also gitignored).

Scope is gmail.readonly: the app never sends mail or modifies the inbox.

Sync is scoped server-side: the Gmail search query only asks for mail from
companies you're actually applying to (any application past `not_applied`)
plus the ATS platforms that send on their behalf (Greenhouse, Lever, …),
over the last year. Nothing outside that filter is ever fetched or read.
Matching messages are parsed (parse_message is pure and offline-tested) and
stored through emailmod.store_message — which links them to applications
and advances `applied → confirmed` on detected confirmations.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

from . import db, emailmod

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

RELEVANT = {"confirmation", "interview", "rejection", "offer"}

# Domains the major ATS platforms send application mail from. Mail from these
# only lands in your inbox if you applied through them, so including them in
# the sender filter is safe — and necessary, because confirmation mail often
# comes from the ATS, not the company's own domain.
ATS_SENDERS = [
    "greenhouse.io", "greenhouse-mail.io", "lever.co", "ashbyhq.com",
    "myworkday.com", "smartrecruiters.com", "icims.com", "eightfold.ai",
    "successfactors.com", "oraclecloud.com",
]


# ----------------------------------------------------------------- credentials
def load_client(data_dir: Path) -> dict | None:
    """The user-created OAuth client ({'installed': {...}} or {'web': {...}})."""
    path = data_dir / CREDENTIALS_FILE
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    client = raw.get("installed") or raw.get("web") or raw
    return client if client.get("client_id") else None


def load_token(data_dir: Path) -> dict | None:
    path = data_dir / TOKEN_FILE
    return json.loads(path.read_text()) if path.exists() else None


def save_token(data_dir: Path, token: dict) -> None:
    existing = load_token(data_dir) or {}
    if "refresh_token" not in token and "refresh_token" in existing:
        token["refresh_token"] = existing["refresh_token"]  # refresh responses omit it
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600)) - 60
    (data_dir / TOKEN_FILE).write_text(json.dumps(token, indent=2))


# ------------------------------------------------------------------ OAuth flow
def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_auth_url(client: dict, redirect_uri: str, state: str) -> str:
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # we need a refresh_token for daily syncs
        "prompt": "consent",
        "state": state,
    })


def exchange_code(client: dict, code: str, redirect_uri: str, data_dir: Path) -> dict:
    import requests
    resp = requests.post(TOKEN_ENDPOINT, data={
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret", ""),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=20)
    resp.raise_for_status()
    token = resp.json()
    save_token(data_dir, token)
    return token


def access_token(data_dir: Path) -> str:
    """Current access token, refreshed through the refresh_token if expired."""
    token = load_token(data_dir)
    if not token:
        raise RuntimeError("not connected — no token.json")
    if time.time() < token.get("expires_at", 0):
        return token["access_token"]
    client = load_client(data_dir)
    if not client or not token.get("refresh_token"):
        raise RuntimeError("token expired and no refresh_token — reconnect Gmail")
    import requests
    resp = requests.post(TOKEN_ENDPOINT, data={
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret", ""),
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    refreshed = resp.json()
    save_token(data_dir, refreshed)
    return refreshed["access_token"]


def connect_account(conn, data_dir: Path) -> str:
    """After a successful exchange: look up the address, record the account."""
    import requests
    profile = requests.get(f"{API}/profile", timeout=20, headers={
        "Authorization": f"Bearer {access_token(data_dir)}"}).json()
    address = profile.get("emailAddress", "")
    row = conn.execute("SELECT id FROM email_accounts WHERE provider = 'gmail' "
                       "AND address = ?", (address,)).fetchone()
    if row:
        conn.execute("UPDATE email_accounts SET status = 'connected' WHERE id = ?", (row["id"],))
    else:
        conn.execute(
            "INSERT INTO email_accounts (provider, address, status, created_at) "
            "VALUES ('gmail', ?, 'connected', ?)", (address, db.utcnow()))
    conn.commit()
    return address


# -------------------------------------------------------------- message parsing
def _decode_body(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _walk_for_text(payload: dict, mime: str) -> str:
    if payload.get("mimeType", "").startswith(mime) and payload.get("body", {}).get("data"):
        return _decode_body(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        text = _walk_for_text(part, mime)
        if text:
            return text
    return ""


def parse_message(raw: dict) -> dict:
    """Gmail API `users.messages.get(format=full)` payload → store_message dict.
    Pure: offline-tested against a fixture payload."""
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _walk_for_text(payload, "text/plain")
    if not body:
        html = _walk_for_text(payload, "text/html")
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()
    sent_at = None
    if headers.get("date"):
        try:
            sent_at = parsedate_to_datetime(headers["date"]).isoformat(timespec="seconds")
        except Exception:  # noqa: BLE001
            pass
    if sent_at is None and raw.get("internalDate"):
        from datetime import datetime, timezone
        sent_at = datetime.fromtimestamp(
            int(raw["internalDate"]) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    return {
        "message_id": raw.get("id", ""),
        "thread_id": raw.get("threadId", ""),
        "from_addr": headers.get("from", ""),
        "to_addr": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "snippet": raw.get("snippet", ""),
        "body": body[:20000],
        "sent_at": sent_at,
    }


def is_job_relevant(conn, message: dict) -> bool:
    """Store only application-related mail: it classified as one of the job
    labels, or it matched a known application by sender/company."""
    if emailmod.classify(message.get("subject", ""), message.get("body", "")) in RELEVANT:
        return True
    app_id, _ = emailmod.match_application(
        conn, message.get("from_addr", ""), message.get("subject", ""),
        message.get("body", ""))
    return app_id is not None


# ------------------------------------------------------------------------ sync
def applied_companies(conn) -> list[str]:
    """Companies with an application in flight — the sender filter for sync."""
    rows = conn.execute(
        """SELECT DISTINCT j.company FROM applications a
           JOIN jobs j ON j.id = a.job_id
           WHERE a.status != 'not_applied' ORDER BY j.company""").fetchall()
    return [r["company"] for r in rows]


def build_query(companies: list[str], lookback_days: int) -> str:
    """Server-side Gmail search: only mail from the companies you're applying
    to (matched on the From header, display name included) or from an ATS
    platform. Pure — offline-tested."""
    terms = [f'"{c}"' if re.search(r"\s", c) else c for c in companies]
    senders = terms + ATS_SENDERS
    return f"newer_than:{lookback_days}d from:({' OR '.join(senders)})"


def purge_unmatched(conn) -> int:
    """Remove previously stored mail the company filter wouldn't have fetched:
    not linked to any application/job and from neither an applied-to company
    nor an ATS sender. Cleans up after the pre-filter sync versions."""
    keep = {t for c in applied_companies(conn) for t in emailmod._company_tokens(c)}
    removed = 0
    for row in conn.execute(
            "SELECT id, from_addr FROM email_messages "
            "WHERE application_id IS NULL AND job_id IS NULL").fetchall():
        sender = row["from_addr"].lower()
        if any(d in sender for d in ATS_SENDERS) or any(t in sender for t in keep):
            continue
        conn.execute("DELETE FROM email_messages WHERE id = ?", (row["id"],))
        removed += 1
    if removed:
        conn.commit()
    return removed


def sync(conn, data_dir: Path, lookback_days: int = 365, max_messages: int = 500) -> dict:
    """Pull mail matching the company filter and store the job-relevant
    messages. Idempotent: store_message dedupes on the Gmail message id."""
    import requests
    headers = {"Authorization": f"Bearer {access_token(data_dir)}"}
    account = conn.execute(
        "SELECT id FROM email_accounts WHERE provider = 'gmail' "
        "AND status = 'connected' LIMIT 1").fetchone()
    counts = {"checked": 0, "stored": 0, "skipped": 0,
              "purged": purge_unmatched(conn)}
    query = build_query(applied_companies(conn), lookback_days)

    page_token = ""
    while counts["checked"] < max_messages:
        params = {"q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        listing = requests.get(f"{API}/messages", params=params,
                               headers=headers, timeout=30).json()
        ids = [m["id"] for m in listing.get("messages", [])]
        if not ids:
            break
        for message_id in ids:
            if counts["checked"] >= max_messages:
                break
            counts["checked"] += 1
            if conn.execute("SELECT 1 FROM email_messages WHERE message_id = ?",
                            (message_id,)).fetchone():
                continue  # already ingested — skip the per-message fetch
            raw = requests.get(f"{API}/messages/{message_id}",
                               params={"format": "full"},
                               headers=headers, timeout=30).json()
            message = parse_message(raw)
            if not is_job_relevant(conn, message):
                counts["skipped"] += 1
                continue
            message["account_id"] = account["id"] if account else None
            emailmod.store_message(conn, message)
            counts["stored"] += 1
        page_token = listing.get("nextPageToken", "")
        if not page_token:
            break
    return counts
