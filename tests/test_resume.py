"""Resume intake: keyword extraction, sample fallback, and the upload route."""

from pathlib import Path

from fastapi.testclient import TestClient

from jobsearch.resume import extract_keywords, load_resume_text
from webapp.app import create_app

SAMPLE = (Path(__file__).parent.parent / "data" / "sample_resume.txt").read_text()


def test_extract_keywords_surfaces_domain_terms():
    keywords = extract_keywords(SAMPLE)
    assert "kubernetes" in keywords
    assert any("distributed systems" in kw or "distributed" in kw for kw in keywords)
    # boilerplate never surfaces
    assert not {"experience", "years", "summary"} & set(keywords)


def test_extract_keywords_prefers_bigrams_over_parts():
    text = "distributed systems design. distributed systems at scale. " * 3
    keywords = extract_keywords(text)
    assert "distributed systems" in keywords
    assert "distributed" not in keywords and "systems" not in keywords


def test_load_resume_text_falls_back_to_sample(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample_resume.txt").write_text("Sample Person\nEngineer\n")
    text, is_sample = load_resume_text(tmp_path, {"resume": "data/resume.txt"})
    assert is_sample and "Sample Person" in text

    (tmp_path / "data" / "resume.txt").write_text("Real Person\nEngineer\n")
    text, is_sample = load_resume_text(tmp_path, {"resume": "data/resume.txt"})
    assert not is_sample and "Real Person" in text


def _client(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "sample_resume.txt").write_text(SAMPLE)
    app = create_app(tmp_path, db_path=tmp_path / "data" / "test.db")
    return TestClient(app)


def test_resume_page_flags_sample_until_upload(tmp_path):
    client = _client(tmp_path)
    page = client.get("/resume").text
    assert "sample resume" in page

    resume = ("Jordan Reviewer\nStaff Software Engineer, Brooklyn, NY\n"
              "jordan@example.org | 555-987-6543\n\nEXPERIENCE\n"
              + "Built search infrastructure with Elasticsearch and Kafka. " * 5)
    resp = client.post("/resume/upload",
                       files={"file": ("resume.txt", resume.encode(), "text/plain")},
                       follow_redirects=False)
    assert resp.status_code == 303 and "uploaded=1" in resp.headers["location"]
    assert "Jordan Reviewer" in (tmp_path / "data" / "resume.txt").read_text()

    page = client.get("/resume").text
    assert "sample resume" not in page
    assert "elasticsearch" in page  # extracted keyword chip


def test_upload_reseeds_profile_fields(tmp_path):
    client = _client(tmp_path)
    resume = ("Jordan Reviewer\nStaff Software Engineer, Brooklyn, NY\n"
              "jordan@example.org\n\n" + "Shipped many systems. " * 10)
    client.post("/resume/upload",
                files={"file": ("resume.txt", resume.encode(), "text/plain")},
                follow_redirects=False)
    page = client.get("/profile").text
    assert "Jordan Reviewer" in page and "jordan@example.org" in page


def test_upload_rejects_wrong_type_and_short_files(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/resume/upload",
                       files={"file": ("resume.docx", b"x" * 500, "application/msword")},
                       follow_redirects=False)
    assert resp.status_code == 303 and "error=" in resp.headers["location"]
    resp = client.post("/resume/upload",
                       files={"file": ("resume.txt", b"too short", "text/plain")},
                       follow_redirects=False)
    assert "error=" in resp.headers["location"]
    assert not (tmp_path / "data" / "resume.txt").exists()
