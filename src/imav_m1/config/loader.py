"""Configuration loading: base.yaml + sites/<site>.yaml + <profile>.yaml.

Two independent dimensions, so any site can be flown in simulation or on the aircraft:

    WHERE   `--site imav | fenswood`     config/sites/<site>.yaml   areas, fence, corridors, ceiling
    HOW     `--profile sim | hardware`   config/<profile>.yaml      link, camera source

Rule (ADR-002): mission code never asks "am I in sim?" or "am I at Fenswood?". It reads values from
the merged config. A site may only make the safety limits in base.yaml MORE conservative, never less
— `effective_max_alt_m()` is the single place that is enforced.
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


def list_sites(config_dir: Path = CONFIG_DIR) -> list[str]:
    d = config_dir / "sites"
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []


def load_config(
    profile: str, site: str | None = None, config_dir: Path = CONFIG_DIR
) -> dict[str, Any]:
    """base.yaml, then the site overlay, then the profile overlay.

    `profile` is added to the result for logging.
    """
    base_path = config_dir / "base.yaml"
    overlay_path = config_dir / f"{profile}.yaml"
    if not overlay_path.exists():
        raise FileNotFoundError(f"No config profile '{profile}' at {overlay_path}")
    cfg = yaml.safe_load(base_path.read_text()) or {}

    site = site or (cfg.get("site") or {}).get("name")
    if site:
        site_path = config_dir / "sites" / f"{site}.yaml"
        if not site_path.exists():
            known = ", ".join(list_sites(config_dir)) or "none found"
            raise FileNotFoundError(f"No site '{site}' at {site_path} (known sites: {known})")
        cfg = _deep_merge(cfg, yaml.safe_load(site_path.read_text()) or {})

    cfg = _deep_merge(cfg, yaml.safe_load(overlay_path.read_text()) or {})
    cfg["profile"] = profile
    return cfg


def effective_max_alt_m(cfg: dict[str, Any]) -> float:
    """The altitude ceiling actually enforced: the tighter of the global cap and the site's own."""
    caps = [float(cfg["safety"]["geofence"]["max_alt_m"])]
    site_cap = (cfg.get("site") or {}).get("max_alt_m")
    if site_cap is not None:
        caps.append(float(site_cap))
    return min(caps)


def effective_fence_action(cfg: dict[str, Any]) -> str:
    """Breach action: the site's, if it names one, else the global default."""
    return str(
        (cfg.get("site") or {}).get("fence_action") or cfg["safety"]["geofence"]["action"]
    ).lower()
