# tests/test_auth.py
import os
from unittest.mock import MagicMock, patch

import pytest

from github_summary.auth import get_token


def test_get_token_uses_gh_cli_first():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "gh_token_12345\n"
    with patch("subprocess.run", return_value=mock_result):
        token = get_token()
    assert token == "gh_token_12345"


def test_get_token_falls_back_to_env_var():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token_67890"}):
            token = get_token()
    assert token == "env_token_67890"


def test_get_token_raises_when_no_auth():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    with patch("subprocess.run", return_value=mock_result):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="No GitHub token found"):
                get_token()


def test_get_token_falls_back_when_gh_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_fallback"}):
            token = get_token()
    assert token == "env_fallback"


def test_get_token_falls_back_when_gh_times_out():
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_timeout_fallback"}):
            token = get_token()
    assert token == "env_timeout_fallback"
