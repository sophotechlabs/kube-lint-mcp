.PHONY: test lint install

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

lint:
	flake8 src/ tests/
