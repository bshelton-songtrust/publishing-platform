# Catalog Management Service - Development Makefile

.PHONY: help setup build start stop clean test lint format migration logs shell

# Default target
help:
	@echo "Available commands:"
	@echo "  setup     - Set up development environment"
	@echo "  build     - Build Docker images"
	@echo "  start     - Start all services"
	@echo "  stop      - Stop all services"
	@echo "  restart   - Restart the catalog service"
	@echo "  clean     - Clean up containers and volumes"
	@echo "  test      - Run tests"
	@echo "  lint      - Run code linting"
	@echo "  format    - Format code"
	@echo "  migration - Create new database migration"
	@echo "  migrate   - Run database migrations"
	@echo "  logs      - Show service logs"
	@echo "  shell     - Open shell in running container"

# Development setup
setup:
	@echo "Setting up development environment..."
	@cp -n .env.example .env || true
	@chmod +x scripts/*.sh
	@./scripts/dev-setup.sh

# Docker operations
build:
	@echo "Building Docker images..."
	@docker-compose build

start:
	@echo "Starting services..."
	@docker-compose up -d

stop:
	@echo "Stopping services..."
	@docker-compose down

restart:
	@echo "Restarting catalog service..."
	@docker-compose restart catalog-service

clean:
	@echo "Cleaning up containers and volumes..."
	@docker-compose down -v
	@docker system prune -f

# Database operations
migrate:
	@echo "Running database migrations..."
	@docker-compose --profile tools run --rm migrate

migration:
	@echo "Creating new migration..."
	@read -p "Enter migration description: " desc; \
	docker-compose exec catalog-service python -m alembic revision --autogenerate -m "$$desc"

# Testing and code quality
test:
	@echo "Running tests..."
	@docker-compose exec catalog-service pytest

test-coverage:
	@echo "Running tests with coverage..."
	@docker-compose exec catalog-service pytest --cov=src --cov-report=html

lint:
	@echo "Running linting..."
	@docker-compose exec catalog-service flake8 src/
	@docker-compose exec catalog-service mypy src/

format:
	@echo "Formatting code..."
	@docker-compose exec catalog-service black src/
	@docker-compose exec catalog-service isort src/

# Development utilities
logs:
	@docker-compose logs -f catalog-service

logs-all:
	@docker-compose logs -f

shell:
	@docker-compose exec catalog-service bash

psql:
	@docker-compose exec postgres psql -U catalog_user -d catalog_management

redis-cli:
	@docker-compose exec redis redis-cli

# Health checks
health:
	@curl -s http://localhost:8000/health | jq .

health-db:
	@curl -s http://localhost:8000/health/database | jq .

# API testing
api-docs:
	@open http://localhost:8000/docs

# Production builds
build-prod:
	@echo "Building production image..."
	@docker build -t catalog-management-service:latest .

# Backup and restore
backup-db:
	@echo "Creating database backup..."
	@docker-compose exec postgres pg_dump -U catalog_user catalog_management > backup_$(shell date +%Y%m%d_%H%M%S).sql

# Install dependencies for local development
install:
	@echo "Installing Python dependencies..."
	@pip install -r requirements.txt
	@pip install -e .

install-dev:
	@echo "Installing development dependencies..."
	@pip install -r requirements.txt
	@pip install pytest pytest-asyncio pytest-cov httpx faker factory-boy
	@pip install black isort flake8 mypy pre-commit

# Pre-commit setup
pre-commit:
	@echo "Setting up pre-commit hooks..."
	@pre-commit install
	@pre-commit run --all-files