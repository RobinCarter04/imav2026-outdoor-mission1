# tools/ — planning and post-flight analysis (not run on the aircraft)
- `coverage_calc.py` — survey time / GSD / line count vs altitude, FOV, overlap, speed for Mapping
  Area 1 (440×280 m) and Area 1+2. Run it before choosing `mission.cruise_alt_m`.

Planned:
- `plot_survey.py`   — flown track from .tlog/.BIN over the planned pattern; coverage gaps.
- `georef_eval.py`   — reported vehicle coordinates vs ground truth; error stats (E-04, 5 m rule).
- `build_map.py`     — pose-tagged images → quick GSD-placed mosaic (must finish well inside 5 min).
- `write_results.py` — emit the Tab. 6 submission table (Vehicle | Identification | lat ; lon).
- `make_run_yaml.py` — create `run.yaml` for a flight folder if the mission code didn't.
