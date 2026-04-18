# GitHub Summary Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that fetches a GitHub user's repos/stats and generates a single self-contained HTML summary page with top-10 rankings, grouped repos, and own-vs-forked breakdown.

**Architecture:** Modular Python package (`github_summary/`) with five focused modules: `auth`, `fetcher`, `grouper`, `renderer`, and `models`. A `generate.py` CLI entrypoint wires them together. A Jinja2 template in `github_summary/templates/` produces the final HTML.

**Tech Stack:** Python 3.10+, `requests`, `PyYAML`, `Jinja2`, `click`, `pytest`

---

## File Map

| File | Purpose |
|------|---------|
| `generate.py` | CLI entrypoint — wires auth → fetch → group → render |
| `requirements.txt` | Runtime dependencies |
| `requirements-dev.txt` | Test/dev dependencies |
| `config.yaml.example` | Example config for users to copy |
| `github_summary/__init__.py` | Empty package marker |
| `github_summary/models.py` | Shared dataclasses: `UserProfile`, `RepoData`, `GroupConfig`, `Config`, `GroupMap` |
| `github_summary/auth.py` | Token resolution: gh CLI → GITHUB_TOKEN env var |
| `github_summary/fetcher.py` | GitHub REST v3 API client — user profile, repos, commit counts |
| `github_summary/grouper.py` | Priority-chain grouper: config → topics → Ollama LLM |
| `github_summary/renderer.py` | Jinja2 renderer — builds context, writes HTML file |
| `github_summary/templates/summary.html.j2` | Self-contained Jinja2 HTML template with inline CSS |
| `.github/workflows/generate.yml` | GitHub Actions: weekly schedule + manual trigger |
| `tests/__init__.py` | Empty |
| `tests/test_auth.py` | Tests for auth module |
| `tests/test_fetcher.py` | Tests for fetcher module |
| `tests/test_grouper.py` | Tests for grouper module |
| `tests/test_renderer.py` | Tests for renderer module |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `config.yaml.example`
- Create: `github_summary/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
requests>=2.31.0
PyYAML>=6.0
Jinja2>=3.1.0
click>=8.1.0
```

- [ ] **Step 2: Create requirements-dev.txt**

```
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 3: Create package and test directories**

```bash
mkdir -p github_summary/templates tests
touch github_summary/__init__.py tests/__init__.py
```

- [ ] **Step 4: Create config.yaml.example**

```yaml
# GitHub Summary Generator — example config
# Copy to config.yaml and fill in your details.

username: your-github-username   # required if not using --username flag
mode: public                     # public (only public repos) | private (all repos)
output: github-summary.html      # output file name
ollama_model: llama3             # Ollama model for auto-grouping

groups:
  AI Tools:
    repos: [repo-a, repo-b]        # explicit repo names
  DevOps:
    topics: [kubernetes, docker]   # match by GitHub topic tag
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Expected: no errors, packages installed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt config.yaml.example github_summary/__init__.py tests/__init__.py
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: Shared Data Models

**Files:**
- Create: `github_summary/models.py`

- [ ] **Step 1: Create models.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

GroupMap = Dict[str, List["RepoData"]]


@dataclass
class UserProfile:
    login: str
    avatar_url: str
    bio: Optional[str]
    location: Optional[str]
    website: Optional[str]
    public_repo_count: int


@dataclass
class RepoData:
    name: str
    description: Optional[str]
    url: str
    stars: int
    forks: int
    updated_at: datetime
    commit_count: int
    language: Optional[str]
    topics: List[str]
    is_fork: bool
    parent_full_name: Optional[str]  # "org/repo" when is_fork=True


@dataclass
class GroupConfig:
    repos: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


@dataclass
class Config:
    username: str
    mode: str  # "public" | "private"
    output: str
    ollama_model: str
    skip_ollama: bool
    groups: Dict[str, GroupConfig] = field(default_factory=dict)
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from github_summary.models import UserProfile, RepoData, Config, GroupConfig, GroupMap; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add github_summary/models.py
git commit -m "feat: add shared data models"
```

---

## Task 3: Auth Module

**Files:**
- Create: `github_summary/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import os
from unittest.mock import MagicMock, patch

import pytest

from github_summary.auth import get_token


def test_get_token_uses_gh_cli_first():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "gh_token_12345\n"
    with patch("subprocess.run", return_value=mock_result):
        token = get_token()
    assert token == "gh_token_12345"


def test_get_token_falls_back_to_env_var():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token_67890"}):
            token = get_token()
    assert token == "env_token_67890"


def test_get_token_raises_when_no_auth():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="No GitHub token found"):
                get_token()


def test_get_token_falls_back_when_gh_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_fallback"}):
            token = get_token()
    assert token == "env_fallback"


def test_get_token_falls_back_when_gh_times_out():
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_timeout_fallback"}):
            token = get_token()
    assert token == "env_timeout_fallback"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `get_token` not yet defined.

- [ ] **Step 3: Implement auth.py**

```python
# github_summary/auth.py
import os
import subprocess


def get_token() -> str:
    """Resolve a GitHub token. Tries gh CLI first, falls back to GITHUB_TOKEN env var."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token

    raise RuntimeError(
        "No GitHub token found.\n"
        "Either:\n"
        "  1. Log in with: gh auth login\n"
        "  2. Set env var: export GITHUB_TOKEN=your_token"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_auth.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add github_summary/auth.py tests/test_auth.py
git commit -m "feat: add auth module with gh CLI and env var fallback"
```

---

## Task 4: GitHub Fetcher

**Files:**
- Create: `github_summary/fetcher.py`
- Create: `tests/test_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fetcher.py
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from github_summary.fetcher import fetch_commit_count, fetch_repos, fetch_user
from github_summary.models import RepoData, UserProfile


def _mock_response(data, status=200, headers=None):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = data
    mock.headers = {"X-RateLimit-Remaining": "100", **(headers or {})}
    mock.raise_for_status = MagicMock()
    return mock


def test_fetch_user_returns_user_profile():
    mock_data = {
        "login": "octocat",
        "avatar_url": "https://github.com/octocat.png",
        "bio": "Developer",
        "location": "San Francisco",
        "blog": "https://example.com",
        "public_repos": 42,
    }
    with patch("requests.get", return_value=_mock_response(mock_data)):
        profile = fetch_user("octocat", "token123")
    assert isinstance(profile, UserProfile)
    assert profile.login == "octocat"
    assert profile.public_repo_count == 42
    assert profile.website == "https://example.com"


def test_fetch_user_handles_null_fields():
    mock_data = {
        "login": "octocat",
        "avatar_url": "https://github.com/octocat.png",
        "bio": None,
        "location": None,
        "blog": None,
        "public_repos": 0,
    }
    with patch("requests.get", return_value=_mock_response(mock_data)):
        profile = fetch_user("octocat", "token")
    assert profile.bio is None
    assert profile.website is None


def test_fetch_repos_returns_list_paginates():
    page1 = [
        {
            "name": "my-repo",
            "description": "A test repo",
            "html_url": "https://github.com/user/my-repo",
            "stargazers_count": 10,
            "forks_count": 2,
            "updated_at": "2026-04-01T00:00:00Z",
            "language": "Python",
            "topics": ["python", "cli"],
            "fork": False,
        }
    ]
    page2 = []
    with patch(
        "requests.get",
        side_effect=[_mock_response(page1), _mock_response(page2)],
    ):
        repos = fetch_repos("user", "token", "public")
    assert len(repos) == 1
    assert isinstance(repos[0], RepoData)
    assert repos[0].name == "my-repo"
    assert repos[0].stars == 10
    assert repos[0].topics == ["python", "cli"]
    assert repos[0].is_fork is False


def test_fetch_repos_includes_fork_parent():
    page1 = [
        {
            "name": "forked-repo",
            "description": None,
            "html_url": "https://github.com/user/forked-repo",
            "stargazers_count": 0,
            "forks_count": 0,
            "updated_at": "2026-04-01T00:00:00Z",
            "language": None,
            "topics": [],
            "fork": True,
            "parent": {"full_name": "original-org/forked-repo"},
        }
    ]
    page2 = []
    with patch(
        "requests.get",
        side_effect=[_mock_response(page1), _mock_response(page2)],
    ):
        repos = fetch_repos("user", "token", "public")
    assert repos[0].is_fork is True
    assert repos[0].parent_full_name == "original-org/forked-repo"


def test_fetch_commit_count_returns_user_total():
    contributors = [
        {"author": {"login": "user"}, "total": 47},
        {"author": {"login": "other"}, "total": 12},
    ]
    with patch("requests.get", return_value=_mock_response(contributors)):
        count = fetch_commit_count("user", "my-repo", "token")
    assert count == 47


def test_fetch_commit_count_returns_zero_if_user_not_contributor():
    contributors = [{"author": {"login": "other"}, "total": 12}]
    with patch("requests.get", return_value=_mock_response(contributors)):
        count = fetch_commit_count("user", "my-repo", "token")
    assert count == 0


def test_fetch_commit_count_retries_on_202():
    mock_202 = _mock_response({}, status=202)
    contributors = [{"author": {"login": "user"}, "total": 5}]
    mock_200 = _mock_response(contributors)
    with patch("requests.get", side_effect=[mock_202, mock_200]):
        with patch("time.sleep"):
            count = fetch_commit_count("user", "repo", "token")
    assert count == 5


def test_fetch_commit_count_gives_up_after_3_retries():
    mock_202 = _mock_response({}, status=202)
    with patch("requests.get", return_value=mock_202):
        with patch("time.sleep"):
            count = fetch_commit_count("user", "repo", "token")
    assert count == 0


def test_fetch_repos_raises_on_rate_limit():
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}
    with patch("requests.get", return_value=_mock_response([], headers=headers)):
        with pytest.raises(RuntimeError, match="rate limit"):
            fetch_repos("user", "token", "public")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fetcher.py -v
```

Expected: `ImportError` — fetcher module not yet created.

- [ ] **Step 3: Implement fetcher.py**

```python
# github_summary/fetcher.py
import time
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
        resp.raise_for_status()

        remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
        if remaining == 0:
            reset = resp.headers.get("X-RateLimit-Reset", "unknown")
            raise RuntimeError(
                f"GitHub rate limit hit. Resets at timestamp {reset}. "
                "Wait and try again."
            )

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
    """Return the authenticated user's total commit count for a repo. Returns 0 if unavailable."""
    url = f"{BASE_URL}/repos/{username}/{repo_name}/stats/contributors"
    for _ in range(3):
        resp = requests.get(url, headers=_headers(token))
        if resp.status_code == 202:
            time.sleep(2)
            continue
        if resp.status_code in (204, 404):
            return 0
        resp.raise_for_status()
        contributors = resp.json()
        if not isinstance(contributors, list):
            return 0
        for c in contributors:
            if c.get("author", {}).get("login", "").lower() == username.lower():
                return c.get("total", 0)
        return 0
    return 0


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetcher.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add github_summary/fetcher.py tests/test_fetcher.py
git commit -m "feat: add GitHub REST API fetcher with pagination and commit counts"
```

---

## Task 5: Repo Grouper

**Files:**
- Create: `github_summary/grouper.py`
- Create: `tests/test_grouper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_grouper.py
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from github_summary.grouper import (
    _group_by_config,
    _group_by_topics,
    group_repos,
)
from github_summary.models import Config, GroupConfig, RepoData


def _repo(name, topics=None, description=None):
    return RepoData(
        name=name,
        description=description or f"{name} description",
        url=f"https://github.com/user/{name}",
        stars=0,
        forks=0,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        commit_count=0,
        language=None,
        topics=topics or [],
        is_fork=False,
        parent_full_name=None,
    )


def _config(groups=None, skip_ollama=True):
    return Config(
        username="user",
        mode="public",
        output="out.html",
        ollama_model="llama3",
        skip_ollama=skip_ollama,
        groups=groups or {},
    )


def test_group_by_config_matches_repo_names():
    repos = [_repo("repo-a"), _repo("repo-b"), _repo("repo-c")]
    groups = {"AI Tools": GroupConfig(repos=["repo-a", "repo-b"], topics=[])}
    result, remaining = _group_by_config(repos, groups)
    assert "AI Tools" in result
    assert len(result["AI Tools"]) == 2
    assert {r.name for r in result["AI Tools"]} == {"repo-a", "repo-b"}
    assert len(remaining) == 1
    assert remaining[0].name == "repo-c"


def test_group_by_config_matches_topics():
    repos = [_repo("repo-a", topics=["docker"]), _repo("repo-b")]
    groups = {"DevOps": GroupConfig(repos=[], topics=["docker"])}
    result, remaining = _group_by_config(repos, groups)
    assert "DevOps" in result
    assert result["DevOps"][0].name == "repo-a"
    assert len(remaining) == 1
    assert remaining[0].name == "repo-b"


def test_group_by_config_repo_not_double_counted():
    repos = [_repo("repo-a", topics=["docker"])]
    groups = {
        "G1": GroupConfig(repos=["repo-a"], topics=[]),
        "G2": GroupConfig(repos=[], topics=["docker"]),
    }
    result, remaining = _group_by_config(repos, groups)
    total = sum(len(v) for v in result.values())
    assert total == 1


def test_group_by_topics_creates_groups_from_repo_topics():
    repos = [
        _repo("repo-a", topics=["python"]),
        _repo("repo-b", topics=["go"]),
        _repo("repo-c", topics=["python"]),
    ]
    result, remaining = _group_by_topics(repos)
    assert "python" in result
    assert len(result["python"]) == 2
    assert "go" in result
    assert len(remaining) == 0


def test_group_by_topics_repos_with_no_topics_remain():
    repos = [_repo("repo-a"), _repo("repo-b", topics=["python"])]
    result, remaining = _group_by_topics(repos)
    assert len(remaining) == 1
    assert remaining[0].name == "repo-a"


def test_group_repos_full_priority_chain():
    repos = [
        _repo("explicit", topics=["python"]),   # config wins
        _repo("by-topic", topics=["python"]),   # topic group
        _repo("ungrouped"),                      # goes to Other
    ]
    groups = {"Manual": GroupConfig(repos=["explicit"], topics=[])}
    config = _config(groups=groups, skip_ollama=True)
    result = group_repos(repos, config)

    assert "Manual" in result
    assert result["Manual"][0].name == "explicit"
    assert "python" in result
    assert result["python"][0].name == "by-topic"
    assert "Other" in result
    assert result["Other"][0].name == "ungrouped"


def test_group_repos_skip_ollama_sends_ungrouped_to_other():
    repos = [_repo("solo")]
    config = _config(skip_ollama=True)
    result = group_repos(repos, config)
    assert "Other" in result
    assert result["Other"][0].name == "solo"


def test_group_repos_ollama_called_when_not_skipped():
    repos = [_repo("unmatched")]
    config = _config(skip_ollama=False)
    fake_llm_result = {"Misc": ["unmatched"]}

    with patch(
        "github_summary.grouper._group_by_llm", return_value={"Misc": repos}
    ) as mock_llm:
        result = group_repos(repos, config)

    mock_llm.assert_called_once()
    assert "Misc" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_grouper.py -v
```

Expected: `ImportError` — grouper module not yet created.

- [ ] **Step 3: Implement grouper.py**

```python
# github_summary/grouper.py
import json
import sys
from typing import Dict, List, Tuple

import requests

from .models import Config, GroupConfig, GroupMap, RepoData


def _group_by_config(
    repos: List[RepoData], groups: Dict[str, GroupConfig]
) -> Tuple[GroupMap, List[RepoData]]:
    result: GroupMap = {}
    used: set = set()

    for group_name, cfg in groups.items():
        matched = []
        for repo in repos:
            if repo.name in used:
                continue
            if repo.name in cfg.repos or any(t in repo.topics for t in cfg.topics):
                matched.append(repo)
                used.add(repo.name)
        if matched:
            result[group_name] = matched

    remaining = [r for r in repos if r.name not in used]
    return result, remaining


def _group_by_topics(repos: List[RepoData]) -> Tuple[GroupMap, List[RepoData]]:
    result: GroupMap = {}
    used: set = set()

    for repo in repos:
        for topic in repo.topics:
            if topic not in result:
                result[topic] = []
            if repo.name not in used:
                result[topic].append(repo)
                used.add(repo.name)

    remaining = [r for r in repos if r.name not in used]
    return result, remaining


def _group_by_llm(repos: List[RepoData], ollama_model: str) -> GroupMap:
    if not repos:
        return {}

    repo_list = "\n".join(
        f"- {r.name}: {r.description or 'no description'}" for r in repos
    )
    prompt = (
        "You are a software developer categorising GitHub repositories. "
        "Group the following repositories into named categories. "
        "Return ONLY a JSON object where keys are category names and values are "
        "lists of repo names. Use 2-5 categories max. "
        "Every repo must appear in exactly one category.\n\n"
        f"Repositories:\n{repo_list}"
    )

    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return {"Other": repos}
        data = json.loads(text[start:end])
        repo_map = {r.name: r for r in repos}
        result: GroupMap = {}
        for group_name, repo_names in data.items():
            matched = [repo_map[n] for n in repo_names if n in repo_map]
            if matched:
                result[group_name] = matched
        return result
    except Exception as e:
        print(f"  Warning: Ollama grouping failed ({e}), skipping.", file=sys.stderr)
        return {"Other": repos}


def group_repos(repos: List[RepoData], config: Config) -> GroupMap:
    result: GroupMap = {}

    # Step 1: config-defined groups (highest priority)
    config_groups, remaining = _group_by_config(repos, config.groups)
    result.update(config_groups)

    # Step 2: GitHub topic auto-grouping
    topic_groups, remaining = _group_by_topics(remaining)
    result.update(topic_groups)

    # Step 3: Ollama LLM grouping (if enabled and Ollama reachable)
    if remaining and not config.skip_ollama:
        llm_groups = _group_by_llm(remaining, config.ollama_model)
        result.update(llm_groups)
        remaining = []

    # Step 4: catch-all
    if remaining:
        result["Other"] = remaining

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grouper.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add github_summary/grouper.py tests/test_grouper.py
git commit -m "feat: add repo grouper with config/topics/Ollama priority chain"
```

---

## Task 6: Jinja2 HTML Template

**Files:**
- Create: `github_summary/templates/summary.html.j2`

- [ ] **Step 1: Create the Jinja2 template**

This is the complete self-contained template. It has no external dependencies — all CSS is inlined.

```html
{# github_summary/templates/summary.html.j2 #}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>@{{ profile.login }} — GitHub Summary</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0d1117; --surface: #161b22; --border: #30363d;
      --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
      --green: #3fb950; --orange: #f78166;
    }
    body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.5; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .container { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem; }

    /* Header */
    header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.5rem 0; }
    .header-inner { display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap; }
    .avatar { width: 72px; height: 72px; border-radius: 50%; border: 2px solid var(--border); flex-shrink: 0; }
    .header-info h1 { font-size: 1.4rem; font-weight: 700; }
    .bio { color: var(--muted); margin-top: 0.25rem; }
    .header-meta { display: flex; gap: 1rem; flex-wrap: wrap; color: var(--muted); font-size: 0.8rem; margin-top: 0.4rem; }
    .header-right { margin-left: auto; text-align: right; font-size: 0.75rem; color: var(--muted); white-space: nowrap; }
    .badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.35rem; }
    .badge.public { background: #1a4731; color: var(--green); }
    .badge.private { background: #3b1f1f; color: var(--orange); }

    /* Sections */
    section { padding: 2rem 0; border-bottom: 1px solid var(--border); }
    section:last-child { border-bottom: none; }
    h2 { font-size: 0.78rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 1rem; }

    /* Rankings */
    .rankings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
    .ranking-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
    .ranking-card h3 { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.75rem; }
    ol.ranking-list { list-style: none; }
    ol.ranking-list li { display: flex; justify-content: space-between; align-items: baseline; padding: 0.3rem 0; border-bottom: 1px solid var(--border); font-size: 0.82rem; }
    ol.ranking-list li:last-child { border-bottom: none; }
    .rank-num { color: var(--muted); font-size: 0.72rem; min-width: 1.4rem; display: inline-block; }
    .stat { color: var(--muted); font-size: 0.72rem; white-space: nowrap; margin-left: 0.5rem; flex-shrink: 0; }

    /* Groups */
    .groups-tags { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .group-tag { background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.75rem; font-size: 0.78rem; color: var(--accent); }
    details.group-detail { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 0.5rem; overflow: hidden; }
    details.group-detail summary { padding: 0.75rem 1rem; cursor: pointer; font-weight: 600; font-size: 0.88rem; list-style: none; display: flex; justify-content: space-between; align-items: center; user-select: none; }
    details.group-detail summary::-webkit-details-marker { display: none; }
    .summary-arrow { color: var(--muted); transition: transform 0.15s; }
    details.group-detail[open] .summary-arrow { transform: rotate(90deg); }
    .group-count { color: var(--muted); font-weight: 400; font-size: 0.8rem; margin-left: 0.5rem; }
    .group-repos-grid { padding: 0 1rem 1rem; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.5rem; }
    .group-repo-item { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.65rem 0.85rem; }
    .repo-name-link { font-weight: 600; font-size: 0.85rem; }
    .repo-desc { color: var(--muted); font-size: 0.78rem; margin-top: 0.2rem; }
    .repo-stats { display: flex; gap: 0.75rem; margin-top: 0.4rem; font-size: 0.72rem; color: var(--muted); }

    /* Repo lists */
    .repo-lists-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5rem; }
    @media (max-width: 768px) { .repo-lists-grid { grid-template-columns: 1fr; } }
    table.repo-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    table.repo-table th { text-align: left; color: var(--muted); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); }
    table.repo-table td { padding: 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    table.repo-table tr:last-child td { border-bottom: none; }
    .repo-desc-small { color: var(--muted); font-size: 0.75rem; margin-top: 0.15rem; }
    .lang-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--muted); margin-right: 3px; vertical-align: middle; }
    .lang-Python { background: #3572A5; } .lang-JavaScript { background: #f1e05a; }
    .lang-TypeScript { background: #2b7489; } .lang-Go { background: #00ADD8; }
    .lang-Rust { background: #dea584; } .lang-Java { background: #b07219; }
    .lang-Ruby { background: #701516; } .lang-Shell { background: #89e051; }
    .lang-C { background: #555555; } .lang-Cpp { background: #f34b7d; }
    .lang-Dart { background: #00B4AB; } .lang-Swift { background: #F05138; }
    .lang-Kotlin { background: #A97BFF; } .lang-PHP { background: #4F5D95; }
    footer { text-align: center; padding: 2rem 0; color: var(--muted); font-size: 0.78rem; border-top: 1px solid var(--border); }
  </style>
</head>
<body>

<header>
  <div class="container">
    <div class="header-inner">
      <img class="avatar" src="{{ profile.avatar_url }}" alt="{{ profile.login }}">
      <div class="header-info">
        <h1><a href="https://github.com/{{ profile.login }}">@{{ profile.login }}</a></h1>
        {% if profile.bio %}<p class="bio">{{ profile.bio }}</p>{% endif %}
        <div class="header-meta">
          {% if profile.location %}<span>📍 {{ profile.location }}</span>{% endif %}
          {% if profile.website %}<a href="{{ profile.website }}">🔗 {{ profile.website }}</a>{% endif %}
          <span>📦 {{ profile.public_repo_count }} public repos</span>
        </div>
      </div>
      <div class="header-right">
        <div>Generated: {{ generated_at }}</div>
        <span class="badge {{ config.mode }}">{{ config.mode }}</span>
      </div>
    </div>
  </div>
</header>

<main>
  <div class="container">

    <!-- Top 10 Rankings -->
    <section>
      <h2>📊 Top 10 Rankings</h2>
      <div class="rankings-grid">

        <div class="ranking-card">
          <h3>🕒 Recently Updated</h3>
          <ol class="ranking-list">
            {% for repo in top_recent %}
            <li>
              <span><span class="rank-num">{{ loop.index }}.</span><a href="{{ repo.url }}">{{ repo.name }}</a></span>
              <span class="stat">{{ repo.updated_at.strftime('%Y-%m-%d') }}</span>
            </li>
            {% endfor %}
          </ol>
        </div>

        <div class="ranking-card">
          <h3>📝 Most Commits</h3>
          <ol class="ranking-list">
            {% for repo in top_commits %}
            <li>
              <span><span class="rank-num">{{ loop.index }}.</span><a href="{{ repo.url }}">{{ repo.name }}</a></span>
              <span class="stat">{{ repo.commit_count }} commits</span>
            </li>
            {% endfor %}
          </ol>
        </div>

        <div class="ranking-card">
          <h3>⭐ Most Starred</h3>
          <ol class="ranking-list">
            {% for repo in top_stars %}
            <li>
              <span><span class="rank-num">{{ loop.index }}.</span><a href="{{ repo.url }}">{{ repo.name }}</a></span>
              <span class="stat">⭐ {{ repo.stars }}</span>
            </li>
            {% endfor %}
          </ol>
        </div>

        <div class="ranking-card">
          <h3>🍴 Most Forked</h3>
          <ol class="ranking-list">
            {% for repo in top_forks %}
            <li>
              <span><span class="rank-num">{{ loop.index }}.</span><a href="{{ repo.url }}">{{ repo.name }}</a></span>
              <span class="stat">🍴 {{ repo.forks }}</span>
            </li>
            {% endfor %}
          </ol>
        </div>

      </div>
    </section>

    <!-- Project Groups -->
    {% if groups %}
    <section>
      <h2>🗂️ Project Groups</h2>
      <div class="groups-tags">
        {% for group_name, group_repos in groups.items() %}
        <span class="group-tag">{{ group_name }} ({{ group_repos | length }})</span>
        {% endfor %}
      </div>
      {% for group_name, group_repos in groups.items() %}
      <details class="group-detail">
        <summary>
          <span>{{ group_name }}<span class="group-count">{{ group_repos | length }} repos</span></span>
          <span class="summary-arrow">▸</span>
        </summary>
        <div class="group-repos-grid">
          {% for repo in group_repos %}
          <div class="group-repo-item">
            <div class="repo-name-link"><a href="{{ repo.url }}">{{ repo.name }}</a></div>
            {% if repo.description %}<div class="repo-desc">{{ repo.description }}</div>{% endif %}
            <div class="repo-stats">
              {% if repo.language %}<span>{{ repo.language }}</span>{% endif %}
              <span>⭐ {{ repo.stars }}</span>
              <span>🍴 {{ repo.forks }}</span>
            </div>
          </div>
          {% endfor %}
        </div>
      </details>
      {% endfor %}
    </section>
    {% endif %}

    <!-- Own Repos & Forks -->
    <section>
      <div class="repo-lists-grid">

        <div>
          <h2>🏠 My Repos ({{ own_repos | length }})</h2>
          <table class="repo-table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Lang</th>
                <th>⭐</th>
                <th>🍴</th>
              </tr>
            </thead>
            <tbody>
              {% for repo in own_repos %}
              <tr>
                <td>
                  <a href="{{ repo.url }}">{{ repo.name }}</a>
                  {% if repo.description %}<div class="repo-desc-small">{{ repo.description }}</div>{% endif %}
                </td>
                <td>
                  {% if repo.language %}
                  <span class="lang-dot lang-{{ repo.language | replace('+', 'p') | replace('#', 'sharp') | replace(' ', '') }}"></span>{{ repo.language }}
                  {% endif %}
                </td>
                <td>{{ repo.stars }}</td>
                <td>{{ repo.forks }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <div>
          <h2>🍴 Forked From Others ({{ forked_repos | length }})</h2>
          <table class="repo-table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Origin</th>
                <th>⭐</th>
              </tr>
            </thead>
            <tbody>
              {% for repo in forked_repos %}
              <tr>
                <td><a href="{{ repo.url }}">{{ repo.name }}</a></td>
                <td>
                  {% if repo.parent_full_name %}
                  <a href="https://github.com/{{ repo.parent_full_name }}" style="color: var(--muted); font-size: 0.78rem">{{ repo.parent_full_name }}</a>
                  {% endif %}
                </td>
                <td>{{ repo.stars }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

      </div>
    </section>

  </div>
</main>

<footer>
  Generated by <a href="https://github.com/wanleung/github-summary">github-summary</a> ·
  <a href="https://github.com/{{ profile.login }}">github.com/{{ profile.login }}</a>
</footer>

</body>
</html>
```

- [ ] **Step 2: Verify the template file exists and is valid Jinja2**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('github_summary/templates'), autoescape=True)
t = env.get_template('summary.html.j2')
print('Template OK')
"
```

Expected output: `Template OK`

- [ ] **Step 3: Commit**

```bash
git add github_summary/templates/summary.html.j2
git commit -m "feat: add self-contained Jinja2 HTML template"
```

---

## Task 7: Renderer Module

**Files:**
- Create: `github_summary/renderer.py`
- Create: `tests/test_renderer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_renderer.py
from datetime import datetime, timezone

from github_summary.models import Config, RepoData, UserProfile
from github_summary.renderer import render


def _profile():
    return UserProfile(
        login="testuser",
        avatar_url="https://example.com/avatar.png",
        bio="Test bio",
        location="Earth",
        website="https://example.com",
        public_repo_count=5,
    )


def _repo(name, stars=0, forks=0, commits=0, is_fork=False, updated_days_ago=0):
    from datetime import timedelta
    return RepoData(
        name=name,
        description=f"{name} description",
        url=f"https://github.com/testuser/{name}",
        stars=stars,
        forks=forks,
        updated_at=datetime(2026, 4, 18, tzinfo=timezone.utc) - timedelta(days=updated_days_ago),
        commit_count=commits,
        language="Python",
        topics=[],
        is_fork=is_fork,
        parent_full_name="org/original" if is_fork else None,
    )


def _config(mode="public"):
    return Config(
        username="testuser",
        mode=mode,
        output="out.html",
        ollama_model="llama3",
        skip_ollama=True,
        groups={},
    )


def test_render_includes_username():
    html = render(_profile(), [_repo("r1")], {}, _config())
    assert "testuser" in html


def test_render_includes_avatar():
    html = render(_profile(), [_repo("r1")], {}, _config())
    assert "https://example.com/avatar.png" in html


def test_render_top_stars_shows_highest():
    repos = [_repo(f"repo-{i}", stars=i) for i in range(15)]
    html = render(_profile(), repos, {}, _config())
    assert "repo-14" in html  # highest starred
    assert "repo-0" not in html  # below top 10


def test_render_top_recent_shows_most_recent():
    repos = [_repo(f"repo-{i}", updated_days_ago=i) for i in range(15)]
    html = render(_profile(), repos, {}, _config())
    assert "repo-0" in html   # most recent (0 days ago)
    assert "repo-14" not in html  # oldest, not in top 10


def test_render_separates_own_and_forked():
    repos = [_repo("mine"), _repo("theirs", is_fork=True)]
    html = render(_profile(), repos, {}, _config())
    assert "mine" in html
    assert "theirs" in html
    assert "org/original" in html


def test_render_shows_groups():
    repos = [_repo("grouped-repo")]
    groups = {"My Group": repos}
    html = render(_profile(), repos, groups, _config())
    assert "My Group" in html
    assert "grouped-repo" in html


def test_render_private_mode_shows_badge():
    html = render(_profile(), [], {}, _config(mode="private"))
    assert 'class="badge private"' in html


def test_render_public_mode_shows_badge():
    html = render(_profile(), [], {}, _config(mode="public"))
    assert 'class="badge public"' in html


def test_render_returns_valid_html_string():
    html = render(_profile(), [_repo("r1")], {}, _config())
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py -v
```

Expected: `ImportError` — renderer not yet created.

- [ ] **Step 3: Implement renderer.py**

```python
# github_summary/renderer.py
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader

from .models import Config, GroupMap, RepoData, UserProfile

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _top10(repos: List[RepoData], key, reverse: bool = True) -> List[RepoData]:
    return sorted(repos, key=key, reverse=reverse)[:10]


def render(
    profile: UserProfile,
    repos: List[RepoData],
    groups: GroupMap,
    config: Config,
) -> str:
    own_repos = sorted(
        [r for r in repos if not r.is_fork],
        key=lambda r: r.updated_at,
        reverse=True,
    )
    forked_repos = sorted(
        [r for r in repos if r.is_fork],
        key=lambda r: r.stars,
        reverse=True,
    )

    context = {
        "profile": profile,
        "config": config,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "top_recent": _top10(repos, key=lambda r: r.updated_at),
        "top_commits": _top10(repos, key=lambda r: r.commit_count),
        "top_stars": _top10(repos, key=lambda r: r.stars),
        "top_forks": _top10(repos, key=lambda r: r.forks),
        "groups": groups,
        "own_repos": own_repos,
        "forked_repos": forked_repos,
    }

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("summary.html.j2")
    return template.render(**context)


def write_output(html: str, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Run all tests to verify nothing is broken**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add github_summary/renderer.py tests/test_renderer.py
git commit -m "feat: add Jinja2 renderer with top-10 rankings and own/forked split"
```

---

## Task 8: CLI Entrypoint

**Files:**
- Create: `generate.py`

- [ ] **Step 1: Create generate.py**

```python
#!/usr/bin/env python3
# generate.py — CLI entrypoint
import sys
from pathlib import Path

import click
import yaml

from github_summary.auth import get_token
from github_summary.fetcher import fetch_all
from github_summary.grouper import group_repos
from github_summary.models import Config, GroupConfig
from github_summary.renderer import render, write_output


def _load_config_file(config_path: str) -> dict:
    p = Path(config_path)
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


@click.command()
@click.option("--username", default=None, help="GitHub username (overrides config)")
@click.option(
    "--mode",
    default=None,
    type=click.Choice(["public", "private"]),
    help="public (default) or private",
)
@click.option("--output", default=None, help="Output HTML path (default: github-summary.html)")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@click.option("--ollama-model", default=None, help="Ollama model name (default: llama3)")
@click.option("--skip-ollama", is_flag=True, default=False, help="Skip LLM grouping")
def main(username, mode, output, config_path, ollama_model, skip_ollama):
    file_cfg = _load_config_file(config_path)

    resolved_username = username or file_cfg.get("username")
    if not resolved_username:
        click.echo(
            "Error: GitHub username is required.\n"
            "Pass --username or set 'username' in config.yaml",
            err=True,
        )
        sys.exit(1)

    resolved_mode = mode or file_cfg.get("mode", "public")
    resolved_output = output or file_cfg.get("output", "github-summary.html")
    resolved_model = ollama_model or file_cfg.get("ollama_model", "llama3")

    raw_groups = file_cfg.get("groups", {}) or {}
    groups = {
        name: GroupConfig(
            repos=cfg.get("repos", []) if cfg else [],
            topics=cfg.get("topics", []) if cfg else [],
        )
        for name, cfg in raw_groups.items()
    }

    config = Config(
        username=resolved_username,
        mode=resolved_mode,
        output=resolved_output,
        ollama_model=resolved_model,
        skip_ollama=skip_ollama,
        groups=groups,
    )

    click.echo(
        f"Fetching GitHub data for @{config.username} ({config.mode} mode)...",
        err=True,
    )

    try:
        token = get_token()
    except RuntimeError as e:
        click.echo(f"Auth error: {e}", err=True)
        sys.exit(1)

    try:
        profile, repos = fetch_all(config.username, token, config.mode)
    except RuntimeError as e:
        click.echo(f"Fetch error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Grouping {len(repos)} repos...", err=True)
    group_map = group_repos(repos, config)

    click.echo("Rendering HTML...", err=True)
    html = render(profile, repos, group_map, config)
    write_output(html, config.output)

    click.echo(f"✓ Generated: {config.output}", err=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help text works**

```bash
python generate.py --help
```

Expected output includes:
```
Usage: generate.py [OPTIONS]

Options:
  --username TEXT
  --mode [public|private]
  --output TEXT
  --config TEXT
  --ollama-model TEXT
  --skip-ollama
  --help
```

- [ ] **Step 3: Run full test suite one more time**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add generate.py
git commit -m "feat: add CLI entrypoint with click"
```

---

## Task 9: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/generate.yml`

- [ ] **Step 1: Create the workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create generate.yml**

```yaml
# .github/workflows/generate.yml
name: Generate GitHub Summary

on:
  schedule:
    - cron: "0 0 * * 0"   # Every Sunday at midnight UTC
  workflow_dispatch:        # Allow manual trigger

permissions:
  contents: write           # Needed to commit the generated file back

jobs:
  generate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Generate summary page
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python generate.py \
            --mode public \
            --skip-ollama \
            --output github-summary.html

      - name: Commit generated file
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add github-summary.html
          if git diff --cached --quiet; then
            echo "No changes to commit."
          else
            git commit -m "chore: regenerate github-summary.html [skip ci]"
            git push
          fi
```

- [ ] **Step 3: Verify YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/generate.yml')); print('YAML OK')"
```

Expected output: `YAML OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/generate.yml
git commit -m "ci: add GitHub Actions workflow for weekly summary generation"
```

---

## Task 10: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# github-summary

Generate a self-contained static HTML page that summarises your GitHub activity — top repos by recency, commits, stars and forks, grouped projects, and a breakdown of your own repos vs forks.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Authenticate (either works)
gh auth login
# OR: export GITHUB_TOKEN=your_personal_access_token

# 3. Copy and edit config
cp config.yaml.example config.yaml
# Edit config.yaml: set your username

# 4. Generate
python generate.py
# Output: github-summary.html
```

## Usage

```
python generate.py [OPTIONS]

Options:
  --username TEXT          GitHub username (overrides config.yaml)
  --mode [public|private]  public = public repos only (default)
                           private = all repos (requires token with repo scope)
  --output PATH            Output file (default: github-summary.html)
  --config PATH            Config file (default: config.yaml)
  --ollama-model TEXT      Ollama model for auto-grouping (default: llama3)
  --skip-ollama            Skip LLM grouping (use config + GitHub topics only)
  --help                   Show help and exit
```

## config.yaml

```yaml
username: your-github-username
mode: public
output: github-summary.html
ollama_model: llama3

groups:
  AI Tools:
    repos: [repo-a, repo-b]      # match by repo name
  DevOps:
    topics: [kubernetes, docker] # match by GitHub topic tag
```

Repos are grouped by priority: **config file → GitHub topics → Ollama LLM → Other**.

## Repo Grouping

| Priority | Source | How |
|----------|--------|-----|
| 1 | `config.yaml` groups | Explicit repo names or topic tags you define |
| 2 | GitHub topics | Repos with matching topic tags auto-grouped |
| 3 | Ollama LLM | Remaining repos clustered by local Ollama model |
| 4 | Other | Any repos still unmatched |

Ollama must be running locally (`ollama serve`). Pass `--skip-ollama` to skip.

## GitHub Actions

The included workflow (`.github/workflows/generate.yml`) regenerates `github-summary.html` every Sunday and commits it back to the repo. No secrets to configure — it uses the built-in `GITHUB_TOKEN`.

To enable, just push the repo to GitHub. Trigger manually from the Actions tab anytime.

## Authentication

| Method | Setup |
|--------|-------|
| GitHub CLI | `gh auth login` |
| Environment variable | `export GITHUB_TOKEN=ghp_...` |

The tool tries `gh auth token` first and falls back to `GITHUB_TOKEN`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with usage, config, and auth instructions"
```

---

## Done

Run `pytest -v` to verify all tests pass before considering the implementation complete.
