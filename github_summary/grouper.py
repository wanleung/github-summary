# github_summary/grouper.py
import json
import shutil
import subprocess
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


_LLM_BATCH_SIZE = 5


def _build_prompt(repos: List[RepoData]) -> str:
    repo_list = "\n".join(
        f"- {r.name}: {r.description or 'no description'}" for r in repos
    )
    return (
        "You are a software developer categorising GitHub repositories. "
        "Group the following repositories into named categories. "
        "Return ONLY a JSON object where keys are category names and values are "
        "lists of repo names. Use 2-5 categories max. "
        "Every repo must appear in exactly one category.\n\n"
        f"Repositories:\n{repo_list}"
    )


def _parse_llm_json(text: str, repos: List[RepoData]) -> GroupMap:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    data = json.loads(text[start:end])
    repo_map = {r.name: r for r in repos}
    result: GroupMap = {}
    for group_name, repo_names in data.items():
        matched = [repo_map[n] for n in repo_names if n in repo_map]
        if matched:
            result[group_name] = matched
    return result


def _call_ollama(repos: List[RepoData], ollama_model: str, ollama_url: str) -> GroupMap:
    prompt = _build_prompt(repos)
    resp = requests.post(
        f"{ollama_url.rstrip('/')}/api/generate",
        json={"model": ollama_model, "prompt": prompt, "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    return _parse_llm_json(resp.json().get("response", ""), repos)


def _call_opencode_go(repos: List[RepoData], model: str, api_key: str) -> GroupMap:
    prompt = _build_prompt(repos)
    resp = requests.post(
        "https://opencode.ai/zen/go/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _parse_llm_json(text, repos)


def _call_opencode_cli(repos: List[RepoData], model: str) -> GroupMap:
    prompt = _build_prompt(repos)
    result = subprocess.run(
        ["opencode", "run", "-m", model, "--format", "json", prompt],
        capture_output=True,
        text=True,
        timeout=60,
    )
    text = ""
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text += event["part"].get("text", "")
        except json.JSONDecodeError:
            continue
    return _parse_llm_json(text, repos)


def _group_by_opencode_cli(repos: List[RepoData], model: str) -> GroupMap:
    if not shutil.which("opencode"):
        print("  Warning: opencode CLI not found in PATH. Skipping.", file=sys.stderr)
        return {}
    return _batch_group(
        repos,
        lambda batch: _call_opencode_cli(batch, model),
        "OpenCode CLI",
    )



    """Quick reachability check — send a trivial 1-repo prompt with a short timeout."""
    try:
        resp = requests.post(
            "https://opencode.ai/zen/go/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": 'Return the JSON: {"test": ["probe"]}'}],
                "max_tokens": 20,
            },
            timeout=15,
        )
        return resp.status_code < 500
    except Exception:
        return False


def _batch_group(
    repos: List[RepoData],
    call_fn,
    label: str,
) -> GroupMap:
    """Split repos into batches, call call_fn per batch, merge results."""
    if not repos:
        return {}

    merged: GroupMap = {}
    batches = [repos[i:i + _LLM_BATCH_SIZE] for i in range(0, len(repos), _LLM_BATCH_SIZE)]
    total = len(batches)

    for idx, batch in enumerate(batches, 1):
        if total > 1:
            print(f"  {label}: batch {idx}/{total} ({len(batch)} repos)...",
                  file=sys.stderr)
        try:
            groups = call_fn(batch)
            for group_name, group_repos in groups.items():
                if group_name in merged:
                    existing = {r.name for r in merged[group_name]}
                    merged[group_name].extend(r for r in group_repos if r.name not in existing)
                else:
                    merged[group_name] = list(group_repos)
        except Exception as e:
            print(f"  Warning: {label} grouping failed on batch {idx} ({e}), skipping batch.",
                  file=sys.stderr)

    return merged


def _group_by_ollama(
    repos: List[RepoData], ollama_model: str, ollama_url: str
) -> GroupMap:
    return _batch_group(
        repos,
        lambda batch: _call_ollama(batch, ollama_model, ollama_url),
        "Ollama",
    )


def _group_by_opencode_go(
    repos: List[RepoData], model: str, api_key: str
) -> GroupMap:
    print("  Checking OpenCode Go connectivity...", file=sys.stderr)
    if not _probe_opencode_go(model, api_key):
        print(
            "  Warning: OpenCode Go is unreachable (check API key and network). Skipping.",
            file=sys.stderr,
        )
        return {}
    return _batch_group(
        repos,
        lambda batch: _call_opencode_go(batch, model, api_key),
        "OpenCode Go",
    )


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

    # Step 3: LLM grouping (if enabled)
    if remaining and not config.skip_ollama:
        if config.llm_provider == "opencode_go" and config.opencode_go_api_key:
            llm_groups = _group_by_opencode_go(
                remaining, config.opencode_go_model, config.opencode_go_api_key
            )
        elif config.llm_provider == "opencode_cli":
            llm_groups = _group_by_opencode_cli(remaining, config.opencode_go_model)
        else:
            llm_groups = _group_by_ollama(
                remaining, config.ollama_model, config.ollama_url
            )
        _merge_into_result(llm_groups)
        assigned = set()
        for repos_in_group in llm_groups.values():
            assigned.update(repo.name for repo in repos_in_group)
        remaining = [repo for repo in remaining if repo.name not in assigned]

    # Step 4: catch-all
    if remaining:
        result["Other"] = remaining

    return result
