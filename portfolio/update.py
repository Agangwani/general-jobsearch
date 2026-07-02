#!/usr/bin/env python3
"""Refresh portfolio/data/activity.json from the GitHub API.

For every project in content.json that has a "repo" ("owner/name"), this pulls
the repo's recent activity — last pushed time, commit counts over the last 7/30
days, star count, and the latest commit subjects — so the portfolio page's
"what's new" text stays current. Run daily by .github/workflows/portfolio.yml.

Standard library only (no pip install needed in CI). Reads GITHUB_TOKEN from the
environment when present (raises the API rate limit and reads private repos);
works unauthenticated against public repos otherwise. API errors never fail the
build — the affected repo is recorded with an "error" and the rest still update.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "data", "content.json")
OUT = os.path.join(HERE, "data", "activity.json")
API = "https://api.github.com"

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
CTX = ssl.create_default_context()


def api_get(path, params=None):
    url = f"{API}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "agangwani-portfolio-updater")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_repo(repo):
    """Return an activity dict for 'owner/name', or {'error': ...}."""
    meta = api_get(f"/repos/{repo}")
    now = datetime.now(timezone.utc)
    since_30 = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff_7 = now - timedelta(days=7)

    commits = api_get(f"/repos/{repo}/commits", {"since": since_30, "per_page": "100"})
    if not isinstance(commits, list):
        commits = []

    def commit_date(c):
        try:
            return datetime.fromisoformat(
                c["commit"]["committer"]["date"].replace("Z", "+00:00")
            )
        except Exception:
            return None

    commits_7d = sum(1 for c in commits if (d := commit_date(c)) and d >= cutoff_7)
    commits_30d = len(commits)

    recent = []
    for c in commits[:5]:
        msg = (c.get("commit", {}).get("message") or "").strip().splitlines()
        recent.append({
            "message": (msg[0] if msg else "")[:90],
            "date": c.get("commit", {}).get("committer", {}).get("date"),
            "url": c.get("html_url"),
        })

    return {
        "pushed_at": meta.get("pushed_at"),
        "description": meta.get("description"),
        "language": meta.get("language"),
        "stars": meta.get("stargazers_count", 0),
        "open_issues": meta.get("open_issues_count", 0),
        "html_url": meta.get("html_url"),
        "commits_7d": commits_7d,
        "commits_30d": commits_30d if commits_30d < 100 else "100+",
        "recent_commits": recent,
    }


def main():
    with open(CONTENT, encoding="utf-8") as f:
        content = json.load(f)

    repos = []
    for p in content.get("projects", []):
        repo = (p.get("repo") or "").strip()
        if repo and "/" in repo and repo not in repos:
            repos.append(repo)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authenticated": bool(TOKEN),
        "repos": {},
    }

    for repo in repos:
        try:
            out["repos"][repo] = fetch_repo(repo)
            print(f"[ok]   {repo}")
        except urllib.error.HTTPError as e:
            out["repos"][repo] = {"error": f"HTTP {e.code}"}
            print(f"[warn] {repo}: HTTP {e.code}", file=sys.stderr)
        except Exception as e:  # network/SSL/parse — keep the build green
            out["repos"][repo] = {"error": str(e)[:200]}
            print(f"[warn] {repo}: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT} ({len(out['repos'])} repos, authenticated={out['authenticated']})")


if __name__ == "__main__":
    main()
