VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: all test lint typecheck install ci clean release

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

BUMP ?= patch

release:
	@LATEST=$$(gh release list --limit 1 --json tagName --jq '.[0].tagName' | sed 's/^v//'); \
	if [ -z "$$LATEST" ]; then echo "ERROR: could not fetch latest release"; exit 1; fi; \
	IFS='.' read -r MAJOR MINOR PATCH <<< "$$LATEST"; \
	case "$(BUMP)" in \
		patch) PATCH=$$((PATCH + 1));; \
		minor) MINOR=$$((MINOR + 1)); PATCH=0;; \
		major) MAJOR=$$((MAJOR + 1)); MINOR=0; PATCH=0;; \
		*) echo "ERROR: BUMP must be patch, minor, or major"; exit 1;; \
	esac; \
	VERSION="$$MAJOR.$$MINOR.$$PATCH"; \
	echo "Latest: v$$LATEST → Next: v$$VERSION ($(BUMP) bump)"; \
	gh workflow run release.yml -f version=$$VERSION

clean:
	rm -rf $(VENV)
