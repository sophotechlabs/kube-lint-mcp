VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: all test lint typecheck install ci clean

all: lint typecheck test

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

install: $(VENV)

test: $(VENV)
	$(PYTHON) -m pytest tests/ -v

lint: $(VENV)
	$(VENV)/bin/ruff check src/ tests/

typecheck: $(VENV)
	$(VENV)/bin/mypy src/

ci: $(VENV)
	$(PYTHON) -m pytest tests/ --cov --cov-report=xml

clean:
	rm -rf $(VENV)
