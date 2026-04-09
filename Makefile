.PHONY: help setup install generate-data deploy test lint clean

help: ## Show all targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create .env from template
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — edit with your values"; else echo ".env already exists"; fi

install: ## Install Python dependencies
	pip install -e ".[dev]"

generate-data: ## Generate synthetic data CSVs to /data
	python -m src.databricks.synthetic_data.generators

deploy: ## Deploy Databricks Asset Bundle
	databricks bundle deploy

deploy-dev: ## Deploy to dev target
	databricks bundle deploy --target dev

deploy-prod: ## Deploy to prod target
	databricks bundle deploy --target prod

test: ## Run tests
	pytest tests/ -v

lint: ## Run linter
	ruff check src/ tests/

format: ## Auto-format code
	ruff format src/ tests/

clean: ## Clean caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name *.egg-info -exec rm -rf {} + 2>/dev/null || true
