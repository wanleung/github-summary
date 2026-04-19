from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

GroupMap = Dict[str, List["RepoData"]]


@dataclass
class UserProfile:
    login: str
    avatar_url: str
    bio: Optional[str]
    location: Optional[str]
    website: Optional[str]
    public_repo_count: int


@dataclass
class RepoData:
    name: str
    description: Optional[str]
    url: str
    stars: int
    forks: int
    updated_at: datetime
    commit_count: int
    language: Optional[str]
    topics: List[str]
    is_fork: bool
    parent_full_name: Optional[str]  # "org/repo" when is_fork=True


@dataclass
class GroupConfig:
    repos: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


@dataclass
class Config:
    username: str
    mode: str  # "public" | "private"
    output: str
    ollama_model: str
    skip_ollama: bool
    ollama_url: str = "http://localhost:11434"
    llm_provider: str = "ollama"          # "ollama" | "opencode_go"
    opencode_go_api_key: str = ""
    opencode_go_model: str = "qwen3.5-plus"
    groups: Dict[str, GroupConfig] = field(default_factory=dict)
