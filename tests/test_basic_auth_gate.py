"""Optional HTTP Basic-auth gate (single-tenant cloud deploys).

Off by default; JOBSEARCH_BASIC_AUTH_PASSWORD turns it on. The AWS App Runner
deploy (deploy/aws-apprunner.sh) relies on this so the public URL isn't wide
open — these tests pin that the env var actually gates every route."""

import base64

from fastapi.testclient import TestClient

from webapp.app import create_app


def _client(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "data" / "resume.txt").write_text("Test User\nSenior Software Engineer\n")
    (tmp_path / "config" / "settings.yaml").write_text(
        "search:\n  query: senior software engineer\n  locations: [new york]\n"
        "ranking:\n  half_life_days: 7\n")
    (tmp_path / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")
    app = create_app(tmp_path, db_path=tmp_path / "data" / "test.db")
    return TestClient(app)


def _basic(user: str, pw: str) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_gate_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBSEARCH_BASIC_AUTH_PASSWORD", raising=False)
    client = _client(tmp_path)
    assert client.get("/").status_code == 200


def test_gate_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_BASIC_AUTH_PASSWORD", "s3cret")
    client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").startswith("Basic")
    # Wrong password and malformed header are rejected too.
    assert client.get("/", headers=_basic("demo", "wrong")).status_code == 401
    assert client.get("/", headers={"Authorization": "Basic !!!not-b64"}).status_code == 401


def test_gate_allows_correct_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_BASIC_AUTH_PASSWORD", "s3cret")
    client = _client(tmp_path)
    assert client.get("/", headers=_basic("demo", "s3cret")).status_code == 200


def test_gate_custom_user(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_BASIC_AUTH_PASSWORD", "s3cret")
    monkeypatch.setenv("JOBSEARCH_BASIC_AUTH_USER", "aman")
    client = _client(tmp_path)
    assert client.get("/", headers=_basic("aman", "s3cret")).status_code == 200
    assert client.get("/", headers=_basic("demo", "s3cret")).status_code == 401
