from datetime import datetime, timedelta, timezone

from jobsearch.models import JobPosting
from jobsearch.scoring import apply_recency, rank_companies, score_jobs

RESUME = """Senior software engineer with AWS Lambda, Step Functions, DynamoDB,
Python microservices, Kafka, distributed systems, fraud detection, observability,
OpenTelemetry, serverless backend architecture, fintech payments."""

BACKEND_DESC = """Build backend microservices in Python on AWS Lambda and DynamoDB.
Event-driven distributed systems with Kafka and SQS. Observability, serverless,
fraud and payments platform experience preferred."""

FRONTEND_DESC = """Craft delightful user interfaces in React and TypeScript.
CSS animation, design systems, accessibility, Figma collaboration, pixel-perfect
web experiences, component libraries, storybook."""


def make_jobs():
    jobs = []
    for i in range(6):
        jobs.append(JobPosting(company=f"Backend{i % 2}", title="Senior Software Engineer, Platform",
                               location="New York", url="", job_id=f"b{i}", description=BACKEND_DESC + f" variant {i}"))
    for i in range(6):
        jobs.append(JobPosting(company=f"Frontend{i % 2}", title="Senior Software Engineer, Web UI",
                               location="New York", url="", job_id=f"f{i}", description=FRONTEND_DESC + f" variant {i}"))
    return jobs


def test_backend_jobs_score_higher():
    jobs = score_jobs(RESUME, make_jobs(), clusters=2)
    backend = [j.fit_score for j in jobs if j.company.startswith("Backend")]
    frontend = [j.fit_score for j in jobs if j.company.startswith("Frontend")]
    assert min(backend) > max(frontend)
    assert all(0 <= j.fit_score <= 100 for j in jobs)
    assert max(j.fit_score for j in jobs) == 100.0


def test_recency_outranks_stale_fit():
    now = datetime.now(timezone.utc)
    fresh = JobPosting(company="A", title="t", location="NY", url="", job_id="1",
                       posted_at=now - timedelta(days=1))
    fresh.fit_score = 70.0
    stale = JobPosting(company="B", title="t", location="NY", url="", job_id="2",
                       posted_at=now - timedelta(days=30))
    stale.fit_score = 95.0
    ordered = apply_recency([stale, fresh], half_life_days=7, unknown_age_days=14)
    assert ordered[0].company == "A"  # fresher posting wins despite lower fit
    assert ordered[0].rank_score > ordered[1].rank_score


def test_rank_companies_uses_top_n():
    jobs = []
    for score in (90, 80, 10, 10):
        job = JobPosting(company="Acme", title="t", location="NY", url="", job_id=str(score))
        job.fit_score = score
        jobs.append(job)
    fit = rank_companies(jobs, top_n=2)
    assert fit["Acme"] == 85.0


def test_full_corpus_scoring():
    """Scored jobs can be a subset of a larger corpus that defines the space."""
    corpus = make_jobs()
    subset = corpus[:3] + corpus[6:9]  # 3 backend + 3 frontend
    subset, topics = score_jobs(RESUME, subset, clusters=2, corpus=corpus, return_topics=True)
    backend = [j.fit_score for j in subset if j.company.startswith("Backend")]
    frontend = [j.fit_score for j in subset if j.company.startswith("Frontend")]
    assert min(backend) > max(frontend)
    assert max(j.fit_score for j in subset) == 100.0
    assert all(j.cluster >= 0 for j in subset)
    assert set(topics) == {0, 1} and all(topics.values())


def test_boilerplate_stripped():
    from jobsearch.scoring import strip_company_boilerplate

    boiler = "Acme is the leading observability platform for cloud infrastructure monitoring."
    jobs = [
        JobPosting(company="Acme", title="SWE", location="NY", url="", job_id=str(i),
                   description=f"{boiler} Role {i}: build the {role} system.")
        for i, role in enumerate(["billing", "search", "ingest"])
    ]
    # A company with a single posting keeps its description untouched.
    solo = JobPosting(company="Solo", title="SWE", location="NY", url="", job_id="s",
                      description=f"{boiler} Unique role.")
    cleaned = strip_company_boilerplate(jobs + [solo])
    for job in jobs:
        assert boiler not in cleaned[job.key]
        assert "system" in cleaned[job.key]  # role-specific text survives
    assert boiler in cleaned[solo.key]


def test_location_excluded_from_vectorized_doc():
    """Location is a hard filter, not a fit signal: city tokens must NOT reach the
    TF-IDF document, or K-means carves out spurious "new york" location clusters
    that bucket strong skill matches by city and demote them."""
    from jobsearch.scoring import _doc

    job = JobPosting(company="Acme", title="Backend Engineer",
                     location="Poughkeepsie, New York", url="", job_id="1",
                     description="Build Python microservices on AWS Lambda.")
    text = _doc(job, {}, {"Acme": None}).lower()
    assert "poughkeepsie" not in text          # the location token is gone
    assert "python microservices" in text      # role text survives
    assert "backend engineer" in text          # title survives


def test_two_jobs_differing_only_in_location_score_equally():
    """Identical postings in different cities must earn the same fit — location
    carries no fit signal (regression guard for the location-skew fix)."""
    desc = BACKEND_DESC + " Platform reliability and payments."
    ny = JobPosting(company="Acme", title="Senior Software Engineer", location="New York",
                    url="", job_id="ny", description=desc)
    sf = JobPosting(company="Acme", title="Senior Software Engineer", location="Remote - Boise, Idaho",
                    url="", job_id="sf", description=desc)
    score_jobs(RESUME, [ny, sf], clusters=1)
    assert ny.fit_score == sf.fit_score


def test_decluster_zeroes_company_signature_but_keeps_cross_company_skills(monkeypatch):
    """A term concentrated in one company (its signature) is zeroed for
    clustering, while a skill term shared across companies survives — so K-means
    groups by skill, not authorship. (Thresholds are relaxed for the tiny test
    corpus; on the real corpus a company's postings are < 5% of the whole.)"""
    import jobsearch.scoring as scoring
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    monkeypatch.setattr(scoring, "COMPANY_SIGNATURE_GLOBAL_DF", 0.6)
    monkeypatch.setattr(scoring, "COMPANY_SIGNATURE_MIN_POSTINGS", 5)

    jobs = []
    for i in range(6):  # Acme: a unique signature word + a shared skill word
        jobs.append(JobPosting(company="Acme", title="e", location="NY", url="",
                               job_id=f"a{i}", description=f"acmesignature python role{i}"))
    for i in range(6):  # others share "python" so it is cross-company (protected)
        jobs.append(JobPosting(company=f"Other{i % 3}", title="e", location="NY", url="",
                               job_id=f"o{i}", description=f"python react role{i}"))
    vec = TfidfVectorizer(min_df=1)
    X = normalize(vec.fit_transform(j.description for j in jobs))
    terms = list(vec.get_feature_names_out())
    stripped = scoring._decluster_company_signatures(X, jobs)

    sig, skill = terms.index("acmesignature"), terms.index("python")
    assert stripped[:6, sig].nnz == 0     # Acme's signature term zeroed on its rows
    assert stripped[:6, skill].nnz == 6   # the cross-company skill term survives

    # Résumé guard: a signature term the résumé itself uses is a real skill, not
    # boilerplate, and must be protected even though it's company-concentrated.
    resume_vec = normalize(vec.transform(["acmesignature is my core skill"])).toarray().ravel()
    guarded = scoring._decluster_company_signatures(X, jobs, resume_vec)
    assert guarded[:6, sig].nnz == 6      # protected because the résumé uses it


def test_boilerplate_changes_scores():
    """Shared marketing text matching the resume must not lift a whole company."""
    boiler = ("We build observability, distributed systems, Kafka, AWS Lambda, "
              "DynamoDB, serverless microservices at massive scale. " * 3)
    jobs = []
    for i in range(4):  # boilerplate-heavy company, role text unrelated to resume
        jobs.append(JobPosting(company="Hype", title="Senior Software Engineer",
                               location="New York", url="", job_id=f"h{i}",
                               description=boiler + f" Role: CSS design systems, marketing pages variant {i}."))
    for i in range(4):  # no boilerplate, genuinely relevant role text
        jobs.append(JobPosting(company="Real", title="Senior Software Engineer",
                               location="New York", url="", job_id=f"r{i}",
                               description=BACKEND_DESC + f" variant {i}"))
    score_jobs(RESUME, jobs, clusters=2)
    hype = max(j.fit_score for j in jobs if j.company == "Hype")
    real = max(j.fit_score for j in jobs if j.company == "Real")
    assert real > hype


# ---------------------------------------- opt-in embedding backend (Stage 4B) ---
def test_embedding_backend_falls_back_to_tfidf_when_unavailable(monkeypatch):
    """match_backend='embedding' with embeddings unavailable must produce the
    same scores as the default TF-IDF path — never crash or zero out."""
    import jobsearch.embeddings as emb
    monkeypatch.setattr(emb, "resume_job_cosine", lambda *a, **k: None)  # unavailable
    tfidf = score_jobs(RESUME, make_jobs(), clusters=2)
    tfidf_scores = [j.fit_score for j in tfidf]
    fallback = score_jobs(RESUME, make_jobs(), clusters=2, match_backend="embedding")
    assert [j.fit_score for j in fallback] == tfidf_scores


def test_embedding_backend_uses_embedding_cosine(monkeypatch):
    """When embeddings are available, the direct similarity term comes from the
    embedding cosine: a job the (faked) model rates highest scores highest."""
    import numpy as np

    import jobsearch.embeddings as emb
    jobs = make_jobs()

    def fake_cosine(resume_text, job_texts, model_name):
        # Rate the last job as the strongest match, everything else weak.
        vals = [0.1] * len(job_texts)
        vals[-1] = 0.99
        return np.array(vals, dtype=float)

    monkeypatch.setattr(emb, "resume_job_cosine", fake_cosine)
    scored = score_jobs(RESUME, jobs, clusters=2, match_backend="embedding")
    assert scored[-1].fit_score == max(j.fit_score for j in scored)   # embedding-driven


def test_embed_texts_none_without_dependency(monkeypatch):
    """embed_texts returns None (not a crash) when sentence-transformers is
    absent — the signal scoring uses to fall back."""
    import builtins

    import jobsearch.embeddings as emb
    emb._MODEL_CACHE.clear()
    real_import = builtins.__import__

    def no_st(name, *a, **k):
        if name.startswith("sentence_transformers"):
            raise ImportError("not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_st)
    assert emb.embed_texts(["hello"], model_name="test-model") is None
    emb._MODEL_CACHE.clear()
