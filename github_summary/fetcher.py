# github_summary/fetcher.py
from datetime import datetime, timezone
from typing import List, Tuple

import requests

from .models import RepoData, UserProfile

BASE_URL = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def fetch_user(username: str, token: str) -> UserProfile:
    resp = requests.get(f"{BASE_URL}/users/{username}", headers=_headers(token))
    resp.raise_for_status()
    d = resp.json()
    return UserProfile(
        login=d["login"],
        avatar_url=d["avatar_url"],
        bio=d.get("bio"),
        location=d.get("location"),
        website=d.get("blog") or None,
        public_repo_count=d["public_repos"],
    )


def fetch_repos(username: str, token: str, mode: str) -> List[RepoData]:
    repos: List[RepoData] = []
    page = 1
    while True:
        if mode == "private":
            url = f"{BASE_URL}/user/repos"
            params = {"per_page": 100, "page": page, "affiliation": "owner"}
        else:
            url = f"{BASE_URL}/users/{username}/repos"
            params = {"per_page": 100, "page": page, "type": "owner"}

        resp = requests.get(url, headers=_headers(token), params=params)

        remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
        if remaining == 0:
            reset = resp.headers.get("X-RateLimit-Reset", "unknown")
            raise RuntimeError(
                f"GitHub rate limit hit. Resets at timestamp {reset}. "
                "Wait and try again."
            )
        resp.raise_for_status()

        batch = resp.json()
        if not batch:
            break

        for r in batch:
            repos.append(
                RepoData(
                    name=r["name"],
                    description=r.get("description"),
                    url=r["html_url"],
                    stars=r["stargazers_count"],
                    forks=r["forks_count"],
                    updated_at=datetime.fromisoformat(
                        r["updated_at"].replace("Z", "+00:00")
                    ),
                    commit_count=0,
                    language=r.get("language"),
                    topics=r.get("topics", []),
                    is_fork=r["fork"],
                    parent_full_name=(
                        r.get("parent", {}).get("full_name") if r["fork"] else None
                    ),
                )
            )
        page += 1

    return repos


def fetch_commit_count(username: str, repo_name: str, token: str) -> int:
    """Return total commit count for a repo by reading pagination Link header."""
    import re

    url = f"{BASE_URL}/repos/{username}/{repo_name}/commits"
    params = {"author": username, "per_page": 1}
    resp = requests.get(url, headers=_headers(token), params=params)
    if resp.status_code in (404, 409):  # 404=not found, 409=empty repo
        return 0
    resp.raise_for_status()
    link = resp.headers.get("Link", "")
    match = re.search(r'page=(\d+)>; rel="last"', link)
    if match:
        return int(match.group(1))
    # No Link header → all commits fit on one page
    data = resp.json()
    return len(data) if isinstance(data, list) else 0


def fetch_all(
    username: str, token: str, mode: str
) -> Tuple[UserProfile, List[RepoData]]:
    import sys

    profile = fetch_user(username, token)
    repos = fetch_repos(username, token, mode)

    own_repos = [r for r in repos if not r.is_fork]
    for i, repo in enumerate(own_repos):
        print(
            f"\r  Fetching commit counts... {i + 1}/{len(own_repos)}",
            end="",
            file=sys.stderr,
        )
        repo.commit_count = fetch_commit_count(username, repo.name, token)
    print(file=sys.stderr)

    return profile, repos
