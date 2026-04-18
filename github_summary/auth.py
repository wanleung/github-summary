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
