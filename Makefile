PYTHON  ?= python3
VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
DUMP    ?= data/sample.bin
ALGO    ?= bpc
ARGS    ?=

.PHONY: help setup test test-fast lint format run validate bench clean distclean

help:
	@echo "make setup      create .venv and install the package + dev tools"
	@echo "make test       run the full test suite"
	@echo "make test-fast  run tests, stop at first failure"
	@echo "make lint       ruff check"
	@echo "make format     ruff format"
	@echo "make run        compress DUMP=<file.bin> with ALGO=<bpc|bdi|stub>, extra flags in ARGS=\"...\""
	@echo "make validate   compare against paper-style results"
	@echo "make bench      time the compressor on DUMP"
	@echo "make clean      remove caches and results"
	@echo "make distclean  clean + remove .venv"

setup: $(VENV)/.installed

$(VENV)/.installed: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	touch $@

test: setup
	$(PY) -m pytest -v

test-fast: setup
	$(PY) -m pytest -q -x

lint: setup
	$(RUFF) check src tests scripts

format: setup
	$(RUFF) format src tests scripts

run: setup
	$(PY) -m compresso.cli $(DUMP) --algo $(ALGO) --out results/ $(ARGS)

validate: setup
	$(PY) scripts/validate_vs_paper.py

bench: setup
	$(PY) scripts/bench.py $(DUMP)

clean:
	rm -rf .pytest_cache .ruff_cache results/*
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

distclean: clean
	rm -rf $(VENV) src/*.egg-info
