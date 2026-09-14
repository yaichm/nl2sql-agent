.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync --extra dev

fmt: ## Format code
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint: ## Lint and type-check
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src

test: ## Run tests
	uv run pytest

up: ## Start postgres, langfuse, mlflow
	docker compose up -d

down: ## Stop services
	docker compose down

seed: ## Download BIRD, convert to postgres, load
	uv run python -m scripts.seed

index: ## Build the schema catalogue and its indexes
	uv run python -m scripts.index_schema

run: ## Start api and ui
	uv run python -m nl2sql_agent.api

eval: ## Full benchmark run
	uv run python -m nl2sql_agent.evaluation.run

eval-quick: ## 30-question smoke set
	uv run python -m nl2sql_agent.evaluation.run --quick

check: lint test ## Everything CI runs

baseline: ## Generer et evaluer la baseline
	uv run nl2sql run --mode baseline --n 50

hybrid: ## Generer et evaluer la recherche hybride
	uv run nl2sql run --mode hybrid --n 50

analyse: ## Comparer les runs et tracer les graphiques
	uv run nl2sql analyse

.PHONY: help install fmt lint test up down seed index run eval eval-quick check
