"""Run directory + run.yaml (E-10): every run is reproducible from commit, profile and config."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def git_commit(cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=5
        )
        sha = out.stdout.strip() or "nogit"
        return sha + ("-dirty" if dirty.stdout.strip() else "")
    except Exception:  # noqa: BLE001
        return "nogit"


def create_run_dir(cfg: dict[str, Any], project_root: Path, name: str = "mission") -> Path:
    base = project_root / cfg.get("logging", {}).get("dir", "data/flights")
    base.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    kind = "hw" if cfg.get("profile") == "hardware" else "sim"
    n = 1 + sum(1 for p in base.iterdir() if p.name.startswith(f"{today}_{kind}_"))
    run_dir = base / f"{today}_{kind}_{n:02d}_{name}"
    run_dir.mkdir()
    # Stable path for anything started separately (the detector, log tails): data/flights/latest
    latest = base / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name)
    except OSError:
        pass  # a symlink is a convenience, never a requirement
    return run_dir


def write_run_yaml(run_dir: Path, cfg: dict[str, Any], project_root: Path, argv: list[str]) -> Path:
    meta = {
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": git_commit(project_root),
        "profile": cfg.get("profile"),
        "python": sys.version.split()[0],
        "argv": argv,
        "config": cfg,
    }
    p = run_dir / "run.yaml"
    p.write_text(yaml.safe_dump(meta, sort_keys=False))
    return p
