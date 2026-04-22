.PHONY: help setup install generate-data build deploy deploy-app deploy-dev deploy-prod test lint format clean

help: ## Show all targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create .env from template
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — edit with your values"; else echo ".env already exists"; fi

install: ## Install Python dependencies
	pip install -e ".[dev]"

generate-data: ## Generate synthetic data CSVs to /data
	python -m src.databricks.synthetic_data.generators

build: ## Build React frontend + Python wheel
	npm run build --prefix app/frontend
	rm -rf dist/*.whl build/ src/*.egg-info
	pip wheel --no-build-isolation --no-deps --no-cache-dir -w dist/ .

BUNDLE_ARGS ?=

deploy: ## Full E2E deploy (build + bundle + setup)
	$(MAKE) build
	databricks bundle deploy $(BUNDLE_ARGS)
	databricks bundle run setup_pipeline $(BUNDLE_ARGS)

deploy-app: ## Redeploy app code only (no setup)
	$(MAKE) build
	databricks bundle deploy $(BUNDLE_ARGS)

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
