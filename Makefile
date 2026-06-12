# ============================================================
# Makefile — lab-playwright-expert
# ============================================================
# Основные команды:
#   make help        — показать все команды
#   make install     — установить зависимости
#   make lint        — запустить линтер
#   make type-check  — проверка типов (mypy)
#   make test        — запустить тесты
#   make test-all    — lint + type-check + test
#   make build       — собрать wheel
#   make docker-build — собрать Docker-образ
#   make run         — запустить через docker-compose
#   make monitoring  — запустить с мониторингом
#   make clean       — очистить артефакты
# ============================================================

.PHONY: help install dev-install lint lint-fix type-check test test-cov test-all build docker-build docker-run run monitoring stop clean pre-commit pre-commit-install

# ─── Переменные ──────────────────────────────────────────────
PYTHON     ?= python3
PIP        ?= pip
RUFF       ?= ruff
MYPY       ?= mypy
PYTEST     ?= pytest
DOCKER     ?= docker
COMPOSE    ?= docker compose

SRC_DIR    := src
TESTS_DIR  := tests
SCRIPTS_DIR := scripts

# ─── Default ─────────────────────────────────────────────────
help: ## Показать список команд
	@echo ""
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║  Lab Playwright Kit — команды сборки             ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ─── Install ─────────────────────────────────────────────────
install: ## Установить production-зависимости
	$(PIP) install -e .

dev-install: ## Установить dev-зависимости
	$(PIP) install -e ".[dev]"
	$(PIP) install pre-commit mypy

# ─── Lint ────────────────────────────────────────────────────
lint: ## Запустить ruff check (src + tests)
	$(RUFF) check $(SRC_DIR)/ $(TESTS_DIR)/

lint-all: ## Запустить ruff check (все файлы)
	$(RUFF) check $(SRC_DIR)/ $(TESTS_DIR)/ $(SCRIPTS_DIR)/

lint-fix: ## Запустить ruff check + автоисправление
	$(RUFF) check --fix $(SRC_DIR)/ $(TESTS_DIR)/ $(SCRIPTS_DIR)/

format: ## Запустить ruff format
	$(RUFF) format $(SRC_DIR)/ $(TESTS_DIR)/ $(SCRIPTS_DIR)/

format-check: ## Проверить форматирование (без изменений)
	$(RUFF) format --check $(SRC_DIR)/ $(TESTS_DIR)/ $(SCRIPTS_DIR)/

# ─── Type Check ──────────────────────────────────────────────
type-check: ## Запустить mypy
	$(MYPY) $(SRC_DIR)/ --ignore-missing-imports --python-version 3.10

# ─── Test ────────────────────────────────────────────────────
test: ## Запустить pytest (быстрый прогон)
	$(PYTEST) $(TESTS_DIR)/ -v --tb=short

test-cov: ## Запустить pytest с coverage
	$(PYTEST) $(TESTS_DIR)/ -v --tb=short \
		--cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

test-quick: ## Запустить только быстрые тесты (без браузера)
	$(PYTEST) $(TESTS_DIR)/ -x -q --tb=line -m "not slow" --no-header

test-all: lint type-check test ## Полный прогон: lint (src+tests) + type-check + test

# ─── Build ───────────────────────────────────────────────────
build: ## Собрать wheel + sdist
	$(PYTHON) -m build

# ─── Docker ──────────────────────────────────────────────────
docker-build: ## Собрать Docker-image
	$(DOCKER) build -t lab-playwright-expert:latest .

docker-build-multi: ## Собрать multi-arch Docker-image (требуется buildx)
	$(DOCKER) buildx build \
		--platform linux/amd64,linux/arm64 \
		-t lab-playwright-expert:latest \
		--load .

docker-run: ## Запустить Docker-контейнер напрямую
	$(DOCKER) run -d \
		--name screenshot-service \
		-p 8190:8190 \
		-e SCREENSHOT_SERVICE_TOKEN=dev-token \
		--restart unless-stopped \
		lab-playwright-expert:latest

docker-stop: ## Остановить Docker-контейнер
	$(DOCKER) stop screenshot-service 2>/dev/null || true
	$(DOCKER) rm screenshot-service 2>/dev/null || true

docker-logs: ## Показать логи контейнера
	$(DOCKER) logs -f screenshot-service

docker-shell: ## Открыть shell в контейнере
	$(DOCKER) exec -it screenshot-service /bin/bash

docker-test: ## Проверить импорты в Docker-образе
	$(DOCKER) run --rm lab-playwright-expert:latest $(PYTHON) -c \
		"from lab_playwright_kit import BrowserManager; print('Import OK')"

# ─── Docker Compose ──────────────────────────────────────────
run: ## Запустить через docker-compose
	$(COMPOSE) up -d

monitoring: ## Запустить с мониторингом (prometheus + grafana)
	$(COMPOSE) --profile monitoring up -d

stop: ## Остановить docker-compose
	$(COMPOSE) down

restart: ## Перезапустить docker-compose
	$(COMPOSE) restart

logs: ## Логи docker-compose
	$(COMPOSE) logs -f

ps: ## Статус сервисов
	$(COMPOSE) ps

# ─── Pre-commit ──────────────────────────────────────────────
pre-commit-install: ## Установить pre-commit хуки
	pre-commit install

pre-commit: ## Запустить pre-commit на всех файлах
	pre-commit run --all-files

# ─── Clean ───────────────────────────────────────────────────
clean: ## Очистить __pycache__, .pytest_cache, dist/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ htmlcov/ .coverage coverage.xml
	rm -f bandit-results.sarif safety-results.json security-audit-results.json
	rm -f pip-audit-results.json trivy-results.sarif
	@echo "✅ Очистка завершена"

clean-all: clean ## Полная очистка (включая Docker)
	$(COMPOSE) down -v --remove-orphans 2>/dev/null || true
	$(DOCKER) rmi lab-playwright-expert:latest 2>/dev/null || true
	@echo "✅ Полная очистка завершена"
