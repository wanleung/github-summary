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
        key=lambda r: (r.updated_at, r.stars),
        reverse=True,
    )[:10]
    forked_repos = sorted(
        [r for r in repos if r.is_fork],
        key=lambda r: r.stars,
        reverse=True,
    )

    context = {
        "profile": profile,
        "config": config,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "top_recent": _top10(repos, key=lambda r: (r.updated_at, r.stars)),
        "top_commits": _top10(repos, key=lambda r: (r.commit_count, r.stars)),
        "top_stars": _top10(repos, key=lambda r: r.stars),
        "top_forks": _top10(repos, key=lambda r: (r.forks, r.stars)),
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
