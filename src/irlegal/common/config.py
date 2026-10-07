"""Load config.yaml from the repository root. Frozen after Phase 0.

Usage:
    from irlegal.common.config import load_config, repo_path
    cfg = load_config()
    toy_dir = repo_path(cfg["paths"]["toy_corpus"])
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def repo_path(*parts: str) -> Path:
    """Absolute path inside the repository."""
    return REPO_ROOT.joinpath(*parts)


@lru_cache(maxsize=1)
def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(repo_path(path), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
