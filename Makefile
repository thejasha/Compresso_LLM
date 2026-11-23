PYTHON  ?= python3
VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
DUMP    ?= data/sample.bin
ALGO    ?= bpc

.PHONY: help setup test test-fast lint format run validate bench clean distclean sim-setup sim-hello sim-writebacks sim-stub-replay

help:
	@echo "make setup      create .venv and install the package + dev tools"
	@echo "make test       run the full test suite"
	@echo "make test-fast  run tests, stop at first failure"
	@echo "make lint       ruff check"
	@echo "make format     ruff format"
	@echo "make run        compress DUMP=<file.bin> with ALGO=<bpc|bdi|stub>"
	@echo "make validate   compare against paper-style results"
	@echo "make bench      time the compressor on DUMP"
	@echo "make clean      remove caches and results"
	@echo "make distclean  clean + remove .venv"
	@echo "make sim-setup      clone and build gem5 (Linux). GEM5_JOBS=2 by default"
	@echo "make sim-hello      run gem5 hello-world"
	@echo "make sim-writebacks   record DRAM writebacks from write_array into data/traces/"
	@echo "make sim-stub-replay  fake control vs Compresso replay on TRACE=data/traces/write_array/writebacks.bin"

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
	mkdir -p results
	$(PY) -m compresso.cli $(DUMP) --algo $(ALGO) --out results/

validate: setup
	$(PY) scripts/validate_vs_paper.py

bench: setup
	$(PY) scripts/bench.py $(DUMP)

clean:
	rm -rf .pytest_cache .ruff_cache results/*
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

distclean: clean
	rm -rf $(VENV) src/*.egg-info

sim-setup:
	bash sim/setup.sh

sim-hello:
	bash sim/run-hello.sh

sim-writebacks:
	bash sim/run-writebacks.sh

TRACE ?= data/traces/write_array/writebacks.bin

sim-stub-replay:
	$(PYTHON) sim/stub_replay.py $(TRACE)
