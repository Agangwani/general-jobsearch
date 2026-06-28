"""Optional Supabase Auth integration (hosted mode).

**Local default — dormant.** With no ``SUPABASE_URL`` / key in the environment
the whole module is inert and the app runs single-user with no login, exactly as
before. Every existing local flow and test is unaffected.

**Hosted mode** (``SUPABASE_URL`` + a Supabase API key set): the app sits behind
a login wall. Credentials are verified by Supabase Auth (GoTrue) over its REST
API; we then keep our *own* signed-cookie session. The app reaches Postgres
through a direct connection (not PostgREST), so it never needs the user's JWT
after login — which keeps this layer small: no JWT verification, no refresh
dance, just "Supabase checked the password, here's who they are."

Until per-user data isolation lands (Stage 2b) every account would share one
dataset, so signups are gated to the first account — the owner. Hosting is then
a private login wall, not yet an open multi-user product.
"""

from __future__ import annotations

import os

import requests

# Identity used in local (non-hosted) mode so downstream code always has a
# stable "current user" without special-casing. Never persisted.
LOCAL_USER = {"id": "local", "email": "local"}

# Paths reachable without a session (auth screens, static assets, health check).
_OPEN_PREFIXES = ("/login", "/signup", "/logout", "/static/", "/healthz", "/favicon")


class AuthError(Exception):
    """A user-facing auth failure (bad credentials, unreachable service, …)."""


def supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").rstrip("/")


def _api_key() -> str:
    return (os.environ.get("SUPABASE_ANON_KEY")
            or os.environ.get("SUPABASE_PUBLISHABLE_KEY") or "")


def is_hosted() -> bool:
    """True when Supabase Auth is configured — i.e. run as a hosted product."""
    return bool(supabase_url() and _api_key())


def is_open_path(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _OPEN_PREFIXES)


def signups_open(conn) -> bool:
    """Whether new signups are accepted. The first (owner) account is always
    allowed; after that signups are closed until per-user isolation (Stage 2b),
    unless explicitly opened with JOBSEARCH_ALLOW_SIGNUPS=1."""
    if os.environ.get("JOBSEARCH_ALLOW_SIGNUPS") == "1":
        return True
    from . import db
    return db.count_app_users(conn) == 0


def session_user(request):
    """The logged-in user dict ({id, email}) or None. In local mode always the
    fixed LOCAL_USER (no auth)."""
    if not is_hosted():
        return LOCAL_USER
    try:
        return request.session.get("user")
    except (AssertionError, AttributeError):
        return None


def current_user_id(request) -> str:
    """The id to scope per-user data by — the logged-in user's id in hosted
    mode, or the local sentinel otherwise. Hosted routes are behind the wall, so
    a real user is always present there; the LOCAL_USER fallback only applies in
    local mode."""
    return (session_user(request) or LOCAL_USER)["id"]


# --------------------------------------------------------------- GoTrue calls ---
def _headers() -> dict:
    key = _api_key()
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> dict:
    try:
        resp = requests.post(f"{supabase_url()}/auth/v1/{path}",
                             json=payload, headers=_headers(), timeout=15)
    except requests.RequestException as exc:
        raise AuthError("Couldn't reach the sign-in service — try again.") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        raise AuthError(str(
            data.get("msg") or data.get("error_description")
            or data.get("error") or data.get("message") or "Authentication failed."))
    return data


def _user_from(data: dict, fallback_email: str) -> dict:
    user = data.get("user") or data
    uid = user.get("id")
    if not uid:
        raise AuthError("Unexpected response from the sign-in service.")
    return {"id": uid, "email": user.get("email") or fallback_email}


def sign_in(email: str, password: str) -> dict:
    """Verify credentials via Supabase. Returns {id, email}; raises AuthError."""
    data = _post("token?grant_type=password", {"email": email, "password": password})
    return _user_from(data, email)


def sign_up(email: str, password: str) -> tuple[dict, bool]:
    """Create an account. Returns ({id, email}, needs_email_confirmation).
    When the project requires email confirmation, no session is returned and the
    second value is True."""
    data = _post("signup", {"email": email, "password": password})
    needs_confirmation = not data.get("access_token")
    return _user_from(data, email), needs_confirmation
