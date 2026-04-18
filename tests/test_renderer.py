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
