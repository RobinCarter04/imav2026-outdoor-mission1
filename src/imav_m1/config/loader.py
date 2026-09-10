"""Configuration loading: base.yaml + <profile>.yaml overlay.

Rule (ADR-002): mission code never asks "am I in sim?". It reads values from the merged config.
Simulation and hardware differ ONLY by which overlay is loaded.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(profile: str, config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    """Return base.yaml merged with <profile>.yaml. Adds `profile` for logging only."""
    base_path = config_dir / "base.yaml"
    overlay_path = config_dir / f"{profile}.yaml"
    if not overlay_path.exists():
        raise FileNotFoundError(f"No config profile '{profile}' at {overlay_path}")
    base = yaml.safe_load(base_path.read_text()) or {}
    overlay = yaml.safe_load(overlay_path.read_text()) or {}
    cfg = _deep_merge(base, overlay)
    cfg["profile"] = profile
    return cfg
