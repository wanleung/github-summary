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
