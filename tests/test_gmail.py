"""Gmail module: message parsing, token handling, relevance gating, and the
OAuth route guards — all offline (no Google calls)."""

import base64
import json

import pytest

from webapp import db, gmail


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


FIXTURE = {
    "id": "msg-1", "threadId": "thr-1", "internalDate": "1760000000000",
    "snippet": "Thanks for applying!",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Datadog Recruiting <no-reply@datadoghq.com>"},
            {"name": "To", "value": "you@example.com"},
            {"name": "Subject", "value": "Your application was received"},
            {"name": "Date", "value": "Fri, 12 Jun 2026 10:00:00 -0400"},
        ],
        "parts": [
            {"mimeType": "text/plain",
             "body": {"data": b64("Thanks for applying to Datadog.\nWe'll be in touch.")}},
            {"mimeType": "text/html",
             "body": {"data": b64("<p>Thanks for applying to <b>Datadog</b>.</p>")}},
        ],
    },
}


def test_parse_message_multipart():
    msg = gmail.parse_message(FIXTURE)
    assert msg["message_id"] == "msg-1" and msg["thread_id"] == "thr-1"
    assert msg["from_addr"].endswith("<no-reply@datadoghq.com>")
    assert msg["subject"] == "Your application was received"
    assert "Thanks for applying to Datadog." in msg["body"]
    assert msg["sent_at"] == "2026-06-12T10:00:00-04:00"


def test_parse_message_html_fallback_and_internal_date():
    raw = {"id": "m2", "internalDate": "1765540800000",
           "payload": {"mimeType": "text/html", "headers": [],
                       "body": {"data": b64("<div>Interview <i>availability</i>?</div>")}}}
    msg = gmail.parse_message(raw)
    assert "Interview" in msg["body"] and "availability" in msg["body"]
    assert "<div>" not in msg["body"]  # tags stripped in the html fallback
    assert msg["sent_at"].startswith("2025-12")  # from internalDate epoch ms


def test_auth_url_and_state():
    client = {"client_id": "abc.apps.googleusercontent.com", "client_secret": "s"}
    url = gmail.build_auth_url(client, "http://127.0.0.1:8484/emails/oauth/callback", "st4te")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=abc.apps.googleusercontent.com" in url
    assert "gmail.readonly" in url
    assert "state=st4te" in url and "access_type=offline" in url


def test_token_save_preserves_refresh_token(tmp_path):
    gmail.save_token(tmp_path, {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
    # a refresh response has no refresh_token — the stored one must survive
    gmail.save_token(tmp_path, {"access_token": "a2", "expires_in": 3600})
    token = gmail.load_token(tmp_path)
    assert token["access_token"] == "a2" and token["refresh_token"] == "r1"
    assert token["expires_at"] > 0


def test_load_client_variants(tmp_path):
    assert gmail.load_client(tmp_path) is None  # no file
    (tmp_path / "credentials.json").write_text(json.dumps(
        {"installed": {"client_id": "x", "client_secret": "y"}}))
    assert gmail.load_client(tmp_path)["client_id"] == "x"


def test_relevance_gating(conn):
    # classified job mail is relevant even with no matching application
    assert gmail.is_job_relevant(conn, {"subject": "Interview availability",
                                        "from_addr": "hr@x.com",
                                        "body": "when are you free for a phone screen?"})
    # plain mail with no application match is not
    assert not gmail.is_job_relevant(conn, {"subject": "Weekly newsletter",
                                            "from_addr": "news@blog.com",
                                            "body": "engineering digest"})


def test_oauth_routes_guarded(tmp_path):
    from fastapi.testclient import TestClient
    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir(); (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text("Test User\nSWE, New York, NY\n")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  title_include: ['x']\n  title_exclude: ['y']\n  locations: [ny]\n"
        "ranking:\n  half_life_days: 7\n")
    (root / "config" / "companies.yaml").write_text("companies: []\nmanual_check: []\n")
    app = create_app(root, db_path=root / "data" / "t.db")
    client = TestClient(app)

    # connect without credentials.json → friendly error, no crash
    resp = client.post("/emails/connect", follow_redirects=False)
    assert resp.status_code == 303 and "error=" in resp.headers["location"]

    # callback with a forged state → rejected
    resp = client.get("/emails/oauth/callback?code=x&state=forged", follow_redirects=False)
    assert resp.status_code == 303 and "error=" in resp.headers["location"]

    # emails page renders the connect button
    page = client.get("/emails").text
    assert "Connect Gmail" in page
