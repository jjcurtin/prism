VENV := .venv

ifeq ($(OS),Windows_NT)
PYTHON := $(VENV)\Scripts\python.exe
PIP := $(VENV)\Scripts\pip.exe
PY_SYS := python
else
PYTHON := $(CURDIR)/$(VENV)/bin/python
PIP := $(VENV)/bin/pip
PY_SYS := python3
endif

.PHONY: setup run interface

.DEFAULT_GOAL := run

ifeq ($(OS),Windows_NT)
# Windows has prebuilt wheels for every requirement (including pandas), so a
# plain venv + pip install is enough.
setup:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	python setup_env.py
else
# pandas has no prebuilt wheel for this platform (cp313/aarch64); install it
# via apt and build the venv with --system-site-packages so pip doesn't try
# (and fail/hang) to compile it from source.
setup:
	sudo apt-get install -y python3-pandas
	python3 -m venv --system-site-packages $(VENV)
	$(PIP) install --upgrade pip
	grep -v '^pandas' requirements.txt | $(PIP) install -r /dev/stdin
	python3 setup_env.py
endif

run:
	$(PY_SYS) stop_server.py
	cd src && $(PYTHON) run_prism.py -mode test

interface:
	cd src && $(PYTHON) prism_interface.py
