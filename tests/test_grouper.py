# tests/test_grouper.py
from datetime import datetime, timezone
from pathlib import Path
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


def _config(groups=None, skip_ollama=True, llm_provider="ollama",
            opencode_go_api_key="", opencode_go_model="qwen3.5-plus"):
    return Config(
        username="user",
        mode="public",
        output="out.html",
        ollama_model="llama3",
        ollama_url="http://localhost:11434",
        skip_ollama=skip_ollama,
        llm_provider=llm_provider,
        opencode_go_api_key=opencode_go_api_key,
        opencode_go_model=opencode_go_model,
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


def test_group_by_topics_does_not_create_empty_groups():
    repos = [_repo("repo-a", topics=["python", "cli"])]
    result, remaining = _group_by_topics(repos)
    assert "python" in result
    assert "cli" not in result
    assert len(remaining) == 0


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
    with patch(
        "github_summary.grouper._group_by_ollama", return_value={"Misc": repos}
    ) as mock_llm:
        result = group_repos(repos, config)

    mock_llm.assert_called_once()
    assert "Misc" in result


def test_group_repos_merges_topic_group_with_same_name():
    repos = [_repo("manual"), _repo("topic-repo", topics=["python"])]
    config = _config(groups={"python": GroupConfig(repos=["manual"], topics=[])})
    result = group_repos(repos, config)
    assert "python" in result
    assert {repo.name for repo in result["python"]} == {"manual", "topic-repo"}


def test_group_repos_preserves_repos_omitted_by_llm():
    repos = [_repo("r1"), _repo("r2")]
    config = _config(skip_ollama=False)
    with patch(
        "github_summary.grouper._group_by_ollama", return_value={"LLM Group": [_repo("r1")]}
    ):
        result = group_repos(repos, config)
    assert "LLM Group" in result
    assert {repo.name for repo in result["LLM Group"]} == {"r1"}
    assert "Other" in result
    assert {repo.name for repo in result["Other"]} == {"r2"}


def test_group_repos_uses_opencode_go_when_provider_set():
    repos = [_repo("unmatched")]
    config = _config(skip_ollama=False, llm_provider="opencode_go",
                     opencode_go_api_key="test-key")
    with patch(
        "github_summary.grouper._group_by_opencode_go", return_value={"Cloud": repos}
    ) as mock_go:
        result = group_repos(repos, config)

    mock_go.assert_called_once_with(repos, "qwen3.5-plus", "test-key",
                                    cache_path=Path(".github-summary-llm-cache.json"))
    assert "Cloud" in result


def test_group_repos_falls_back_to_ollama_if_no_go_key():
    repos = [_repo("unmatched")]
    config = _config(skip_ollama=False, llm_provider="opencode_go", opencode_go_api_key="")
    with patch("github_summary.grouper._group_by_ollama", return_value={"Misc": repos}) as mock_ollama:
        with patch("github_summary.grouper._group_by_opencode_go") as mock_go:
            result = group_repos(repos, config)

    mock_ollama.assert_called_once()
    mock_go.assert_not_called()
    assert "Misc" in result


def test_group_repos_uses_opencode_cli_when_provider_set():
    repos = [_repo("unmatched")]
    config = _config(skip_ollama=False, llm_provider="opencode_cli",
                     opencode_go_model="opencode-go/qwen3.5-plus")
    with patch(
        "github_summary.grouper._group_by_opencode_cli", return_value={"Tools": repos}
    ) as mock_cli:
        result = group_repos(repos, config)

    mock_cli.assert_called_once_with(repos, "opencode-go/qwen3.5-plus",
                                     cache_path=Path(".github-summary-llm-cache.json"))
    assert "Tools" in result
