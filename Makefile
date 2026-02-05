.PHONY: test lint install ci

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

lint:
	flake8 src/ tests/

ci:
	python -m pytest tests/ --cov --cov-report=xml
