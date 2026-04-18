# GitHub Summary Generator — Design Document

**Date:** 2026-04-18  
**Status:** Approved

---

## Problem Statement

Open source developers accumulate many repositories over time. It is hard for visitors (and the developers themselves) to understand:
- What the developer is currently working on
- Which repos they have contributed to
- How repos relate to each other

This tool generates a single, self-contained static HTML page that summarises a GitHub user's activity and repos in a clear, structured way.

---

## Goals

- Generate a single self-contained HTML file (no external dependencies)
- Support **public mode** (public repos only) and **private mode** (all repos)
- Show top 10 rankings across 4 dimensions
- Group related repos using a priority chain: config file → GitHub topics → Ollama LLM
- List own repos and forked repos separately
- Run on-demand via CLI or automatically via GitHub Actions

---

## Architecture

**Approach:** Modular Python package with a CLI entrypoint.

```
github-summary/
├── generate.py                    # CLI entrypoint
├── config.yaml                    # User config (optional)
├── requirements.txt
├── github_summary/
│   ├── __init__.py
│   ├── auth.py                    # Token resolution
│   ├── fetcher.py                 # GitHub REST API client
│   ├── grouper.py                 # Repo grouping pipeline
│   ├── renderer.py                # Jinja2 → HTML
│   ├── models.py                  # Shared dataclasses
│   └── templates/
│       └── summary.html.j2        # Jinja2 template (inline CSS+JS)
└── .github/
    └── workflows/
        └── generate.yml           # GitHub Actions workflow
```

Each module has a single responsibility and communicates through the typed models defined in `models.py`.

---

## Modules

### `models.py`
Shared dataclasses used across all modules:
- `UserProfile` — avatar_url, login, bio, location, website, public_repo_count
- `RepoData` — name, description, url, stars, forks, updated_at, commit_count, language, topics, is_fork, parent_full_name
- `Config` — username, mode, output, ollama_model, skip_ollama, groups
- `GroupMap` — `Dict[str, List[RepoData]]`

### `auth.py`
Resolves a GitHub token in order:
1. Run `gh auth token` — use stdout if exit code 0
2. Fall back to `GITHUB_TOKEN` environment variable
3. Raise a clear error if neither is available

### `fetcher.py`
Fetches all required data from the GitHub REST v3 API using the resolved token:
- User profile (`GET /users/{username}`)
- All repositories with pagination (`GET /users/{username}/repos`)
- In private mode: uses authenticated `GET /user/repos` instead
- Commit count per repo via contributor stats (`GET /repos/{owner}/{repo}/stats/contributors`) — extracts the authenticated user's total
- Filters to public-only repos in public mode
- Returns `UserProfile` and `List[RepoData]`
- Handles rate limiting: checks `X-RateLimit-Remaining`, waits on 202 (stats not ready) with retry

### `grouper.py`
Applies a priority chain to assign repos to named groups:

1. **Config file groups** — explicit `repo: [name, ...]` or `topics: [tag, ...]` mappings in `config.yaml`. Repos matched here are removed from the ungrouped pool.
2. **GitHub topics auto-grouping** — remaining repos with matching topics are grouped by topic name.
3. **Ollama LLM grouping** — remaining ungrouped repos (name + description) are sent to a local Ollama model with a prompt asking it to cluster them into named groups. Skipped if `--skip-ollama` is set or if Ollama is unreachable.
4. **Ungrouped** — any remaining repos go into an implicit "Other" group.

Returns a `GroupMap`.

### `renderer.py`
Takes `UserProfile`, `List[RepoData]`, `GroupMap`, and `Config`. Computes:
- Top 10 by `updated_at`
- Top 10 by `commit_count`
- Top 10 by `stars`
- Top 10 by `forks`
- Own repos (not fork) sorted by updated_at
- Forked repos sorted by stars descending

Renders `summary.html.j2` via Jinja2 and writes a single HTML file with all CSS and JS inlined.

### `generate.py` (CLI)
```
usage: generate.py [options]

options:
  --username TEXT        GitHub username (overrides config)
  --mode [public|private]
  --output PATH          Output HTML file (default: github-summary.html)
  --config PATH          Config file (default: config.yaml)
  --ollama-model TEXT    Ollama model name (default: llama3)
  --skip-ollama          Skip LLM grouping step
```

Wires auth → fetch → group → render in sequence. Prints progress to stderr.

---

## Generated Page Structure

```
┌─────────────────────────────────────────────────────────┐
│  Avatar  @username · Bio · Location · Website           │
│                              Generated: Apr 2026 · Mode │
├─────────────────────────────────────────────────────────┤
│  📊 Top 10 Rankings                                      │
│  [Recently Updated] [Most Commits] [Most ⭐] [Most 🍴]  │
├─────────────────────────────────────────────────────────┤
│  🗂️ Project Groups                                       │
│  [AI Tools (4)]  [DevOps (3)]  [Mobile (2)]  …          │
│  ▼ AI Tools: repo-a · repo-b · repo-c                   │
├─────────────────────────────────────────────────────────┤
│  🏠 My Repos (32)          │  🍴 Forked From Others (14) │
│  repo · ⭐12 · Python      │  org/repo · ⭐2.1k          │
└─────────────────────────────────────────────────────────┘
```

Public mode: private repos are excluded silently.  
Private mode: all repos included; page header shows a "Private" badge.

---

## `config.yaml` Schema

```yaml
username: your-github-username     # required if not passed via CLI
mode: public                       # public | private
output: github-summary.html
ollama_model: llama3

groups:
  AI Tools:
    repos: [repo-a, repo-b]        # explicit repo names
  DevOps:
    topics: [kubernetes, docker]   # match by GitHub topic tag
```

Groups defined here take priority over topic auto-grouping and LLM grouping.

---

## GitHub Actions Workflow

File: `.github/workflows/generate.yml`

Triggers:
- `schedule` — weekly (Sunday midnight UTC)
- `workflow_dispatch` — manual trigger

Steps:
1. Checkout repo
2. Set up Python
3. Install dependencies (`pip install -r requirements.txt`)
4. Run generator: `python generate.py --mode public --skip-ollama`
   - Uses built-in `GITHUB_TOKEN` secret
5. Commit and push `github-summary.html` back to repo (if changed)

Note: `--skip-ollama` is always passed in CI since Ollama is not available. Grouping uses config + topics only in the Actions environment.

---

## Authentication

| Method | How |
|--------|-----|
| `gh` CLI | `gh auth token` — reuses existing gh login |
| Environment variable | `GITHUB_TOKEN` env var |
| Priority | gh CLI first, env var fallback |
| Failure | Clear error message with instructions for both methods |

---

## Error Handling

- **Auth failure** — print instructions for both auth methods, exit 1
- **Rate limit hit** — print remaining reset time, exit 1
- **Ollama unreachable** — warn and skip LLM step, continue with config+topics
- **Repo stats not ready (202)** — retry up to 3 times with 2s delay, skip if still not ready
- **Missing config.yaml** — not an error; all config can come from CLI flags

---

## Dependencies

```
requests          # GitHub REST API calls
PyYAML            # config.yaml parsing
Jinja2            # HTML template rendering
click             # CLI argument parsing
```

No dependency on PyGithub — direct REST calls keep it lightweight and auditable.

---

## Extension Points

- **New grouping strategy** — add a function to `grouper.py` and insert into the priority chain
- **New output format** — add a renderer module alongside `renderer.py`
- **New data source** — add a fetcher module and extend `models.py` as needed
- **Different LLM** — `grouper.py` LLM call is isolated; swap Ollama for any OpenAI-compatible endpoint

---

## Out of Scope (MVP)

- Interactive web UI
- Diff/changelog between runs
- Contribution graphs or heatmaps
- Organisation-level summaries
