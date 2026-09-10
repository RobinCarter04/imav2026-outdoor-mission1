"""Architecture rules that are cheap to enforce mechanically (ADR-003)."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "imav_m1"


def test_pymavlink_only_imported_in_vehicle_package():
    offenders = []
    for py in SRC.rglob("*.py"):
        if "vehicle" in py.parts:
            continue
        text = py.read_text()
        if "pymavlink" in text and "import" in text:
            for line in text.splitlines():
                if "pymavlink" in line and line.strip().startswith(("import", "from")):
                    offenders.append(f"{py.relative_to(SRC)}: {line.strip()}")
    assert not offenders, "pymavlink may only be imported inside vehicle/:\n" + "\n".join(offenders)


def test_no_profile_branching_in_mission_code():
    """Mission logic must not do `if profile == 'sim'` — differences live in config (ADR-002)."""
    offenders = []
    for py in SRC.rglob("*.py"):
        if py.name in ("cli.py", "loader.py", "run_meta.py"):
            continue
        for line in py.read_text().splitlines():
            if "profile" in line and ("==" in line or "!=" in line):
                offenders.append(f"{py.relative_to(SRC)}: {line.strip()}")
    assert not offenders, "\n".join(offenders)
