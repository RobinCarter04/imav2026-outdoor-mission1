# IMAV 2026 Outdoor Mission 1 — common tasks.  `make help` lists targets.
.PHONY: help setup test test-sitl lint fmt sitl-setup launch stop sitl sitl-stop gcs-bridge mission-sim mission-sim-auto plan-sim replay check-config preflight

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

help:               ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

setup:              ## create venv and install package with dev + sitl extras
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev,sitl]"

test:               ## unit tests (fast, no SITL). Must be green before any hardware work.
	$(PY) -m pytest

test-sitl:          ## integration tests against a running SITL
	$(PY) -m pytest -m sitl

lint:               ## ruff lint + format check
	$(VENV)/bin/ruff check src tests tools
	$(VENV)/bin/ruff format --check src tests tools

fmt:                ## auto-format
	$(VENV)/bin/ruff format src tests tools
	$(VENV)/bin/ruff check --fix src tests tools

sitl-setup:         ## one-time per laptop: find or build the ArduPilot SITL binary
	./scripts/setup_sitl.sh

launch:             ## ONE COMMAND: SITL + mission (+ Mission Planner bridge with GCS=<host>), one Terminal window each
	./scripts/launch_sim.sh $(if $(GCS),--gcs $(GCS)) $(if $(KML),--kml $(KML)) $(if $(SITE),--site $(SITE)) $(ARGS)

stop:               ## stop SITL, the GCS bridge and the mission
	./scripts/stop_sim.sh

sitl:               ## start ArduPilot SITL headless (sim/README.md). SPEEDUP=5 WIPE=1 optional
	./scripts/start_sitl.sh

sitl-stop:          ## stop SITL
	./scripts/stop_sitl.sh

gcs-bridge:         ## MAVProxy bridge SITL -> Mission Planner in the VM: make gcs-bridge GCS=<host-or-ip>
	./scripts/mavproxy_gcs_bridge.sh $(or $(GCS),ROBINCARTERC2F9.local)

mission-sim:        ## run the mission against SITL with the operator dashboard (http://localhost:5000)
	$(PY) -m imav_m1.cli run --profile sim

mission-sim-auto:   ## scripted headless run against SITL (setup -> preflight -> start -> results)
	$(PY) -m imav_m1.cli run --profile sim --auto --no-gui

plan-sim:           ## offline survey plan + preview SVG for the sim area
	$(PY) -m imav_m1.cli plan --profile sim

replay:             ## run detection over a recorded video, no vehicle
	$(PY) -m imav_m1.cli replay --profile sim

check-config:       ## print the merged config for a profile (PROFILE=sim|hardware)
	$(PY) -m imav_m1.cli check-config --profile $(or $(PROFILE),sim)

preflight:          ## hardware preflight checks (run on the Pi before every real flight)
	./scripts/preflight.sh
