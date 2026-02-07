.PHONY: test lint typecheck install ci

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

ci:
	python -m pytest tests/ --cov --cov-report=xml
