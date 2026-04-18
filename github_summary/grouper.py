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
            if repo.name not in used:
                if topic not in result:
                    result[topic] = []
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

    def _merge_into_result(groups: GroupMap) -> None:
        for group_name, grouped_repos in groups.items():
            if group_name in result:
                existing = {repo.name for repo in result[group_name]}
                result[group_name].extend(
                    repo for repo in grouped_repos if repo.name not in existing
                )
            else:
                result[group_name] = list(grouped_repos)

    # Step 1: config-defined groups (highest priority)
    config_groups, remaining = _group_by_config(repos, config.groups)
    _merge_into_result(config_groups)

    # Step 2: GitHub topic auto-grouping
    topic_groups, remaining = _group_by_topics(remaining)
    _merge_into_result(topic_groups)

    # Step 3: Ollama LLM grouping (if enabled and Ollama reachable)
    if remaining and not config.skip_ollama:
        llm_groups = _group_by_llm(remaining, config.ollama_model)
        _merge_into_result(llm_groups)
        assigned = set()
        for repos_in_group in llm_groups.values():
            assigned.update(repo.name for repo in repos_in_group)
        remaining = [repo for repo in remaining if repo.name not in assigned]

    # Step 4: catch-all
    if remaining:
        result["Other"] = remaining

    return result
