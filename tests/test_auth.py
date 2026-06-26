"""Tests for hosted-mode Supabase Auth (webapp/auth.py + the login wall).

Local mode (no SUPABASE_* env) is exercised by the rest of the suite, which
hits routes without any login — proving the wall is inert by default. These
tests force hosted mode via env and stub the GoTrue network call, so no real
Supabase is contacted."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from webapp import auth
from webapp.app import create_app


def test_local_mode_is_unauthenticated(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert auth.is_hosted() is False
    # In local mode there is no wall and the "user" is a fixed local identity
    # (session_user never even touches the request object).
    assert auth.session_user(None) == auth.LOCAL_USER


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    """A TestClient for the app in hosted (Supabase Auth) mode, backed by a
    fresh SQLite db so account state is isolated per test."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    app = create_app(tmp_path, db_path=tmp_path / "data" / "auth.db")
    return TestClient(app)


def _app_users(tmp_path):
    db = sqlite3.connect(tmp_path / "data" / "auth.db")
    db.row_factory = sqlite3.Row
    try:
        return db.execute("SELECT * FROM app_users").fetchall()
    finally:
        db.close()


def _stub_login(monkeypatch, uid="uuid-owner", email="owner@example.com"):
    monkeypatch.setattr(auth, "_post", lambda path, payload: {
        "access_token": "x", "user": {"id": uid, "email": email}})


def test_wall_redirects_anonymous_to_login(hosted):
    r = hosted.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_and_static_pages_are_open(hosted):
    assert hosted.get("/login").status_code == 200
    assert "Log in" in hosted.get("/login").text
    assert hosted.get("/healthz").json() == {"ok": True}


def test_login_sets_session_and_first_user_is_owner(hosted, tmp_path, monkeypatch):
    _stub_login(monkeypatch)
    r = hosted.post("/login", data={"email": "owner@example.com", "password": "pw"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    # Session now lets the wall through.
    assert hosted.get("/").status_code == 200
    rows = _app_users(tmp_path)
    assert len(rows) == 1
    assert rows[0]["email"] == "owner@example.com"
    assert rows[0]["is_admin"] == 1  # first account becomes the owner/admin


def test_signups_close_after_the_owner_exists(hosted, monkeypatch):
    assert 'name="email"' in hosted.get("/signup").text  # open before any account
    _stub_login(monkeypatch)
    hosted.post("/login", data={"email": "o@e.com", "password": "pw"})
    assert "closed" in hosted.get("/signup").text.lower()  # closed after owner


def test_signup_requiring_confirmation_shows_message(hosted, monkeypatch):
    # GoTrue with email-confirmation on returns a bare user (no access_token).
    monkeypatch.setattr(auth, "_post", lambda path, payload: {
        "id": "uuid-new", "email": "new@example.com",
        "confirmation_sent_at": "2026-01-01T00:00:00Z"})
    r = hosted.post("/signup",
                    data={"email": "new@example.com", "password": "password1"},
                    follow_redirects=False)
    assert r.status_code == 200
    assert "confirm" in r.text.lower()


def test_bad_credentials_show_an_error(hosted, monkeypatch):
    def boom(path, payload):
        raise auth.AuthError("Invalid login credentials")
    monkeypatch.setattr(auth, "_post", boom)
    r = hosted.post("/login", data={"email": "x@y.com", "password": "nope"},
                    follow_redirects=False)
    assert r.status_code == 400
    assert "Invalid login credentials" in r.text
