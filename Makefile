.PHONY: help install install-dev test test-coverage lint format check clean build docs docker-build docker-run setup pre-commit

# Default target
help: ## Show this help message
	@echo "Content Collector - Development Commands"
	@echo "========================================"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Installation
install: ## Install production dependencies
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install

# Testing
test: ## Run all tests
	python -m pytest tests/ -v

test-unit: ## Run unit tests only
	python -m pytest tests/unit/ -v

test-integration: ## Run integration tests only
	python -m pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests only
	python -m pytest tests/e2e/ -v

test-coverage: ## Run tests with coverage report
	python -m pytest tests/ --cov=src/content_collector --cov-report=html --cov-report=term-missing --cov-report=xml

test-fast: ## Run tests excluding slow tests
	python -m pytest tests/ -v -m "not slow"

# Code Quality
lint: ## Run all linters
	python -m flake8 src/ tests/
	python -m mypy src/ --ignore-missing-imports
	python -m bandit -r src/

format: ## Format code with black and isort
	python -m black src/ tests/
	python -m isort src/ tests/

format-check: ## Check formatting without making changes
	python -m black --check src/ tests/
	python -m isort --check-only src/ tests/

check: format-check lint test ## Run all checks (format, lint, test)

# Security
security: ## Run security checks
	python -m bandit -r src/
	python -m safety check

# Documentation
docs: ## Generate documentation
	cd docs && make html

docs-serve: ## Serve documentation locally
	cd docs/_build/html && python -m http.server 8000

# Database
db-upgrade: ## Run database migrations
	alembic upgrade head

db-downgrade: ## Rollback database migration
	alembic downgrade -1

db-migration: ## Create new migration (use: make db-migration MESSAGE="description")
	alembic revision --autogenerate -m "$(MESSAGE)"

db-reset: ## Reset database (WARNING: destroys all data)
	rm -f test_data/content_collector.db
	alembic upgrade head

# Development
dev-setup: install-dev db-upgrade ## Complete development setup
	@echo "Development environment ready!"

run-example: ## Run example scraping job
	python -m content_collector.cli.main run test_data/tmickley_input.txt --depth 2

clean: ## Clean up build artifacts and caches
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Docker
docker-build: ## Build Docker image
	docker build -t content-collector .

docker-run: ## Run application in Docker
	docker-compose up

docker-test: ## Run tests in Docker
	docker-compose -f docker/docker-compose.test.yml up --abort-on-container-exit

# Release
build: clean ## Build distribution packages
	python -m build

release-test: build ## Upload to test PyPI
	python -m twine upload --repository testpypi dist/*

release: build ## Upload to PyPI
	python -m twine upload dist/*

# Git hooks
pre-commit: ## Run pre-commit hooks manually
	pre-commit run --all-files

pre-commit-update: ## Update pre-commit hooks
	pre-commit autoupdate

# Monitoring
status: ## Check application status
	python -m content_collector.cli.main status

logs: ## View recent logs
	tail -f logs/content_collector.log

# Performance
profile: ## Run performance profiling
	python -m cProfile -o profile.stats -m content_collector.cli.main run test_data/tmickley_input.txt
	python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"

benchmark: ## Run benchmarks
	python -m pytest tests/benchmarks/ -v --benchmark-only

# Environment
env-check: ## Check environment and dependencies
	python --version
	pip list | grep -E "(content-collector|pytest|black|isort|flake8|mypy)"
	python -c "import content_collector; print('✓ Package importable')"

env-create: ## Create virtual environment
	python -m venv venv
	@echo "Activate with: source venv/bin/activate"

# All-in-one commands
ci: format-check lint security test-coverage ## Run full CI pipeline
	@echo "✓ All CI checks passed!"

dev: format lint test ## Quick development cycle
	@echo "✓ Development checks passed!"

quick: format test-fast ## Quick checks for development
	@echo "✓ Quick checks passed!"
