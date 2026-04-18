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
