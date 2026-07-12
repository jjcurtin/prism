VENV := .venv

ifeq ($(OS),Windows_NT)
PYTHON := $(VENV)\Scripts\python.exe
PY_SYS := python
else
PYTHON := $(CURDIR)/$(VENV)/bin/python
PY_SYS := python3
endif

.PHONY: help setup run-silent run-live interface test-server test-client test-all test-integration typecheck

.DEFAULT_GOAL := help

# No target given: delegate to tasks.py's own no-args help (avoids
# maintaining two separate lists of available commands).
help:
	$(PY_SYS) tasks.py

# Create .venv and install all dependencies (system python -- no venv exists yet).
setup:
	$(PY_SYS) tasks.py setup

# Stop any running server and start PRISM in silent mode (no real texts sent).
run-silent:
	$(PYTHON) tasks.py run --mode silent

# Stop any running server and start PRISM in live mode (sends real texts).
run-live:
	$(PYTHON) tasks.py run --mode live

# Launch the RA terminal interface.
interface:
	$(PYTHON) tasks.py interface

# Server-side suite: config loading, task scheduling, participant
# management, coordinator SMS alerting on system failures.
test-server:
	$(PYTHON) tasks.py test server

# Interface-side tests: full user_interface_menus/ coverage (phase 04).
test-client:
	$(PYTHON) tasks.py test client

# Full offline test suite: server + client + integration.
test-all:
	$(PYTHON) tasks.py test all

# real end-to-end tests against real external services (Qualtrics,
# the research drive) using real dev-environment credentials -- local-only,
# not run in CI, skips cleanly if dev credentials aren't configured here.
# See tests_integration/README.md.
test-integration:
	$(PYTHON) tasks.py test integration

# Static type check of src/ via mypy (see mypy.ini). Gradual/non-strict;
# tests/, tests_interface/, tests_integration/ are out of scope for now.
typecheck:
	$(PYTHON) tasks.py typecheck
