# Makefile for Triangular Arbitrage Trading System
# All targets are idempotent and display the commands they run

.DEFAULT_GOAL := help
.PHONY: help setup test lint type fmt validate backtest paper metrics docker-build docker-test clean

# Configuration
PYTHON := python3
PIP := pip
PROJECT_NAME := triangular-arbitrage
DOCKER_IMAGE := $(PROJECT_NAME)
TEST_PATH := tests/
SOURCE_PATH := triangular_arbitrage/

# Colors for output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

help: ## Show this help message
	@echo "$(CYAN)Triangular Arbitrage Trading System$(RESET)"
	@echo "$(CYAN)====================================$(RESET)"
	@echo ""
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install development dependencies and pre-commit hooks
	@echo "$(CYAN)Setting up development environment...$(RESET)"
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e .
	pre-commit install
	@echo "$(GREEN)✅ Development environment ready$(RESET)"

test: ## Run the test suite with coverage
	@echo "$(CYAN)Running test suite...$(RESET)"
	$(PYTHON) -m pytest $(TEST_PATH) -v --cov=$(SOURCE_PATH) --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✅ Tests completed$(RESET)"

lint: ## Run linting checks (flake8)
	@echo "$(CYAN)Running linting checks...$(RESET)"
	$(PYTHON) -m flake8 $(SOURCE_PATH) tests/ --max-line-length=88 --extend-ignore=E203,W503
	@echo "$(GREEN)✅ Linting passed$(RESET)"

type: ## Run type checking (mypy)
	@echo "$(CYAN)Running type checks...$(RESET)"
	$(PYTHON) -m mypy $(SOURCE_PATH) --ignore-missing-imports
	@echo "$(GREEN)✅ Type checking passed$(RESET)"

fmt: ## Format code with black and isort
	@echo "$(CYAN)Formatting code...$(RESET)"
	$(PYTHON) -m black $(SOURCE_PATH) tests/ --line-length=88
	$(PYTHON) -m isort $(SOURCE_PATH) tests/ --profile=black
	@echo "$(GREEN)✅ Code formatted$(RESET)"

validate: lint type ## Run all validation checks (lint + type)
	@echo "$(GREEN)✅ All validation checks passed$(RESET)"

backtest: ## Run backtesting mode with example strategy
	@echo "$(CYAN)Running backtest mode...$(RESET)"
	$(PYTHON) run_strategy.py --strategy configs/strategies/strategy_robust_example.yaml --mode backtest
	@echo "$(GREEN)✅ Backtest completed$(RESET)"

paper: ## Run paper trading mode with example strategy  
	@echo "$(CYAN)Running paper trading mode...$(RESET)"
	$(PYTHON) run_strategy.py --strategy configs/strategies/strategy_robust_example.yaml --mode paper
	@echo "$(GREEN)✅ Paper trading completed$(RESET)"

metrics: ## Start metrics server for monitoring
	@echo "$(CYAN)Starting metrics server...$(RESET)"
	$(PYTHON) -c "from triangular_arbitrage.metrics import MetricsServer; import asyncio; asyncio.run(MetricsServer().start_server())"

docker-build: ## Build Docker image
	@echo "$(CYAN)Building Docker image...$(RESET)"
	docker build -t $(DOCKER_IMAGE):latest .
	@echo "$(GREEN)✅ Docker image built: $(DOCKER_IMAGE):latest$(RESET)"

docker-test: docker-build ## Run tests inside Docker container
	@echo "$(CYAN)Running tests in Docker container...$(RESET)"
	docker run --rm $(DOCKER_IMAGE):latest
	@echo "$(GREEN)✅ Docker tests completed$(RESET)"

docker-dev: ## Start development environment with Docker Compose
	@echo "$(CYAN)Starting development environment...$(RESET)"
	docker-compose -f docker-compose.dev.yml up -d
	@echo "$(GREEN)✅ Development environment started$(RESET)"

docker-down: ## Stop development environment
	@echo "$(CYAN)Stopping development environment...$(RESET)"
	docker-compose -f docker-compose.dev.yml down
	@echo "$(GREEN)✅ Development environment stopped$(RESET)"

clean: ## Clean up build artifacts and caches
	@echo "$(CYAN)Cleaning up...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ htmlcov/ .coverage .mypy_cache/ 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup completed$(RESET)"

# Development workflow targets
dev-setup: setup ## Complete development setup
	@echo "$(GREEN)🚀 Development environment is ready!$(RESET)"
	@echo "$(YELLOW)Try: make test && make validate$(RESET)"

ci: validate test ## Run all CI checks locally
	@echo "$(GREEN)✅ All CI checks passed$(RESET)"

# Release targets
build: clean ## Build distribution packages
	@echo "$(CYAN)Building distribution packages...$(RESET)"
	$(PYTHON) -m build
	@echo "$(GREEN)✅ Distribution packages built$(RESET)"

check-build: build ## Check distribution packages
	@echo "$(CYAN)Checking distribution packages...$(RESET)"
	$(PYTHON) -m twine check dist/*
	@echo "$(GREEN)✅ Distribution packages verified$(RESET)"
