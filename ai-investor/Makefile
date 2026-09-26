PY ?= .venv/bin/python

.PHONY: install check lint type test run

install:
	uv venv .venv && uv pip install --python $(PY) -e ".[dev]"

lint:
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

type:
	$(PY) -m mypy

test:
	$(PY) -m pytest

check: lint type test

run:
	$(PY) -m ai_investor.main
