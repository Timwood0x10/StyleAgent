.PHONY: help install lint format typecheck test clean

help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Format code with ruff"
	@echo "  make typecheck    - Run mypy type checker"
	@echo "  make test         - Run tests"
	@echo "  make clean        - Clean cache files"

install:
	pip install -r requirements.txt
	pip install ruff mypy pytest pytest-cov

lint:
	ruff check src/ tests/ examples/

format:
	ruff format src/ tests/ examples/

typecheck:
	mypy src/

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .coverage htmlcov
