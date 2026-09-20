from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS = ROOT / "docs"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings(path: Path | None = None) -> dict:
    s = load_yaml(path or ROOT / "config" / "settings.yaml")
    from .guards import assert_read_only
    assert_read_only(s)
    return s


def load_sources(path: Path | None = None) -> dict:
    return load_yaml(path or ROOT / "config" / "sources.yaml")["sources"]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()
