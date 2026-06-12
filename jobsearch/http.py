from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def make_session(timeout: int = 30) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    session.request_timeout = timeout  # type: ignore[attr-defined]
    return session


def get_json(session: requests.Session, url: str, **kwargs):
    kwargs.setdefault("timeout", getattr(session, "request_timeout", 30))
    resp = session.get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


def post_json(session: requests.Session, url: str, **kwargs):
    kwargs.setdefault("timeout", getattr(session, "request_timeout", 30))
    resp = session.post(url, **kwargs)
    resp.raise_for_status()
    return resp.json()
