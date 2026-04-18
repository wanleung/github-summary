# tests/test_fetcher.py
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
import requests

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


def test_fetch_repos_raises_runtime_error_before_http_error_on_rate_limit():
    mock_resp = _mock_response(
        [],
        status=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"},
    )
    mock_resp.raise_for_status.side_effect = requests.HTTPError("forbidden")
    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="rate limit"):
            fetch_repos("user", "token", "public")
