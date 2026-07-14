#!/usr/bin/env bash
# parsing_cron.sh — Единый скрипт парсинга для всех агентов лаборатории
# Используется из cron и вручную для тестовых запусков.
#
# Использование:
#   ./scripts/parsing_cron.sh <agent_name> [options]
#   ./scripts/parsing_cron.sh bestia --dry-run
#   ./scripts/parsing_cron.sh all
#
# Агенты: bestia, voron, kotolizator, sova, streikbrecher

set -euo pipefail

PROJECT_DIR="/root/LabDoctorM/projects/lab-playwright-expert"
PYTHON="python3"
PYTHONPATH="src"
LOG_DIR="/root/LabDoctorM/.ops/logs/parsing"
TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)

# ─── Цвета для вывода ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── Утилиты ──────────────────────────────────────────────────────────────────

log() {
    local level="$1"
    shift
    local msg="$*"
    local color=""
    case "$level" in
        INFO)  color="$GREEN" ;;
        WARN)  color="$YELLOW" ;;
        ERROR) color="$RED" ;;
        DEBUG) color="$BLUE" ;;
    esac
    echo -e "${color}[$(date +%H:%M:%S)] [${level}]${NC} ${msg}"
    mkdir -p "$LOG_DIR"
    echo "[$(date +%Y-%m-%dT%H:%M:%S)] [${level}] ${msg}" >> "${LOG_DIR}/${AGENT:-unknown}_${TIMESTAMP}.log"
}

die() {
    log ERROR "$*"
    exit 1
}

# ─── Проверка окружения ──────────────────────────────────────────────────────

check_env() {
    cd "$PROJECT_DIR" || die "Не удалось перейти в $PROJECT_DIR"

    if [ ! -d "src/lab_playwright_kit" ]; then
        die "Не найден src/lab_playwright_kit. Проверьте что вы в правильной директории."
    fi

    # Проверяем что orchestrator импортируется
    if ! PYTHONPATH="$PYTHONPATH" $PYTHON -c "from lab_playwright_kit.parsing_orchestrator import ParsingOrchestrator" 2>/dev/null; then
        die "Не удалось импортировать ParsingOrchestrator. Проверьте зависимости."
    fi

    log INFO "✅ Окружение OK (PYTHONPATH=$PYTHONPATH)"
}

# ─── Агент: Бестия ────────────────────────────────────────────────────────────

run_bestia() {
    local dry_run="${1:-false}"
    log INFO "🐾 Бестия (СнабЛаб) — Запуск парсинга госзакупок"

    if [ "$dry_run" = "true" ]; then
        log INFO "[DRY RUN] Бестия — пропускаем реальный парсинг"
        return 0
    fi

    export AGENT_NAME="bestia"

    # Парсинг закупок по ключевым словам
    local keywords=("стройка" "оборудование" "медицина")
    for keyword in "${keywords[@]}"; do
        log INFO "Парсинг закупок: keyword=$keyword"
        PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    url = 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=${keyword}&morphology=on&pageNumber=1'
    result = await parse_url(url, schema='zakupki', stealth='advanced', max_pages=10, timeout=120)
    print(f'Status: {result.status.value}, Items: {result.items_count}, Duration: {result.duration_seconds:.1f}s')
    if result.errors:
        print(f'Errors: {result.errors[:3]}')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
            log INFO "  → $line"
        done

        # Пауза между запросами (rate limit)
        sleep 3
    done

    log INFO "✅ Бестия — Парсинг завершён"
}

# ─── Агент: Ворон ─────────────────────────────────────────────────────────────

run_voron() {
    local dry_run="${1:-false}"
    log INFO "🐦 Ворон (lab-monitoring) — Запуск мониторинга AI-инструментов"

    if [ "$dry_run" = "true" ]; then
        log INFO "[DRY RUN] Ворон — пропускаем реальный парсинг"
        return 0
    fi

    export AGENT_NAME="voron"

    local sources=(
        "https://openai.com/blog|OpenAI Blog|извлечь все новые продукты, обновления, изменения в API, цены"
        "https://blog.google/technology/ai/|Google AI Blog|извлечь все AI-анонсы, новые модели, обновления Gemini"
        "https://www.anthropic.com/news|Anthropic News|извлечь все анонсы Claude, новые модели, обновления safety"
    )

    for source in "${sources[@]}"; do
        IFS='|' read -r url name query <<< "$source"
        log INFO "Парсинг: $name ($url)"

        PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    result = await parse_url('${url}', schema='${query}', parser_type='llm_parser', stealth='standard', timeout=60)
    print(f'Status: {result.status.value}, Items: {result.items_count}, Duration: {result.duration_seconds:.1f}s')
    if result.errors:
        print(f'Errors: {result.errors[:2]}')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
            log INFO "  → $line"
        done

        sleep 2
    done

    log INFO "✅ Ворон — Мониторинг завершён"
}

# ─── Агент: Котолизатор ──────────────────────────────────────────────────────

run_kotolizator() {
    local dry_run="${1:-false}"
    log INFO "🐱 Котолизатор (VPN) — Запуск мониторинг VPN-панелей"

    if [ "$dry_run" = "true" ]; then
        log INFO "[DRY RUN] Котолизатор — пропускаем реальный парсинг"
        return 0
    fi

    export AGENT_NAME="kotolizator"

    # Проверка IP через ipify
    log INFO "Проверка IP-адреса через ipify.org..."
    PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    result = await parse_url('https://api.ipify.org?format=json', schema='generic', stealth='none', timeout=10)
    print(f'Status: {result.status.value}, Items: {result.items_count}')
    if result.data:
        print(f'IP Data: {result.data[0]}')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
        log INFO "  → $line"
    done

    # Проверка доступности Google
    log INFO "Проверка доступности google.com..."
    PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    result = await parse_url('https://google.com', schema='generic', stealth='none', timeout=15)
    print(f'Status: {result.status.value}, Duration: {result.duration_seconds:.1f}s')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
        log INFO "  → $line"
    done

    log INFO "✅ Котолизатор — Мониторинг завершён"
}

# ─── Агент: Сова ──────────────────────────────────────────────────────────────

run_sova() {
    local dry_run="${1:-false}"
    log INFO "🦉 Сова (autoexpert) — Запуск парсинга автозапчастей"

    if [ "$dry_run" = "true" ]; then
        log INFO "[DRY RUN] Сова — пропускаем реальный парсинг"
        return 0
    fi

    export AGENT_NAME="sova"

    # Тестовый запрос
    local query="${2:-BMW X5}"
    log INFO "Поиск: $query"

    PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    result = await parse_url('https://www.autodoc.ru/', schema='auto_parts', parser_type='auto_parts_spider', stealth='standard', timeout=60)
    print(f'Status: {result.status.value}, Items: {result.items_count}, Duration: {result.duration_seconds:.1f}s')
    if result.errors:
        print(f'Errors: {result.errors[:2]}')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
        log INFO "  → $line"
    done

    log INFO "✅ Сова — Парсинг завершён"
}

# ─── Агент: Стрейкбрехер ─────────────────────────────────────────────────────

run_streikbrecher() {
    local dry_run="${1:-false}"
    log INFO "⚡ Стрейкбрехер (fullstack) — Запуск парсинга тестовых данных"

    if [ "$dry_run" = "true" ]; then
        log INFO "[DRY RUN] Стрейкбрехер — пропускаем реальный парсинг"
        return 0
    fi

    export AGENT_NAME="streikbrecher"

    local test_sites=(
        "https://the-internet.herokuapp.com/|The Internet"
        "https://demoqa.com/|DemoQA"
    )

    for site in "${test_sites[@]}"; do
        IFS='|' read -r url name <<< "$site"
        log INFO "Парсинг тестового сайта: $name ($url)"

        PYTHONPATH="$PYTHONPATH" $PYTHON -c "
import asyncio
from lab_playwright_kit.parsing_orchestrator import parse_url

async def main():
    result = await parse_url('${url}', schema='generic', parser_type='data_parser', stealth='none', timeout=30)
    print(f'Status: {result.status.value}, Items: {result.items_count}, Duration: {result.duration_seconds:.1f}s')
    if result.data:
        print(f'Keys: {list(result.data[0].keys())[:8]}')

asyncio.run(main())
" 2>&1 | while IFS= read -r line; do
            log INFO "  → $line"
        done

        sleep 1
    done

    log INFO "✅ Стрейкбрехер — Парсинг завершён"
}

# ─── Запуск всех агентов ─────────────────────────────────────────────────────

run_all() {
    local dry_run="${1:-false}"
    log INFO "🚀 Запуск ВСЕХ агентов (dry_run=$dry_run)"

    run_bestia "$dry_run"
    echo "---"
    run_voron "$dry_run"
    echo "---"
    run_kotolizator "$dry_run"
    echo "---"
    run_sova "$dry_run"
    echo "---"
    run_streikbrecher "$dry_run"

    log INFO "🏁 Все агенты завершили работу"
}

# ─── Метрики ──────────────────────────────────────────────────────────────────

show_metrics() {
    log INFO "📊 Метрики парсинга (Prometheus format):"
    PYTHONPATH="$PYTHONPATH" $PYTHON -c "
from lab_playwright_kit.parsing_orchestrator import ParsingOrchestrator
o = ParsingOrchestrator()
print(o.get_prometheus_metrics())
"
}

# ─── Тест импортов ────────────────────────────────────────────────────────────

test_imports() {
    log INFO "🧪 Тест импортов всех парсеров..."
    PYTHONPATH="$PYTHONPATH" $PYTHON -c "
from lab_playwright_kit.parsing_orchestrator import (
    ParsingOrchestrator,
    ParseTask,
    ParseResult,
    ParseStatus,
    ParsePriority,
    ParserType,
    StealthLevel,
    ParsingMetrics,
    SOURCE_REGISTRY,
    NICHE_TO_PARSER,
    parse_url,
    parse_batch,
)
print('✅ Все импорты OK')
print(f'   SOURCE_REGISTRY: {len(SOURCE_REGISTRY)} источников')
print(f'   NICHE_TO_PARSER: {len(NICHE_TO_PARSER)} схем')
print(f'   ParserTypes: {[e.value for e in ParserType]}')
"
}

# ─── Главная логика ────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
Использование: $0 <agent|all|test|metrics> [options]

Агенты:
  bestia        Парсинг госзакупок (zakupki.gov.ru)
  voron         Мониторинг AI-инструментов (changelog)
  kotolizator   Мониторинг VPN-панелей
  sova          Парсинг автозапчастей
  streikbrecher Парсинг тестовых данных для E2E

Команды:
  all           Запуск всех агентов
  test          Тест импортов (без реального парсинга)
  metrics       Показать метрики Prometheus

Опции:
  --dry-run     Без реального парсинга (проверка конфигурации)
  --query <q>   Поисковый запрос (для Совы)

Примеры:
  $0 bestia
  $0 bestia --dry-run
  $0 voron
  $0 sova --query \"Toyota Camry\"
  $0 all
  $0 test
EOF
}

main() {
    local command="${1:-help}"
    shift || true

    local dry_run="false"
    local query=""

    # Парсинг аргументов
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                dry_run="true"
                shift
                ;;
            --query)
                query="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    case "$command" in
        bestia)
            check_env
            run_bestia "$dry_run"
            ;;
        voron)
            check_env
            run_voron "$dry_run"
            ;;
        kotolizator)
            check_env
            run_kotolizator "$dry_run"
            ;;
        sova)
            check_env
            run_sova "$dry_run" "$query"
            ;;
        streikbrecher)
            check_env
            run_streikbrecher "$dry_run"
            ;;
        all)
            check_env
            run_all "$dry_run"
            ;;
        test)
            check_env
            test_imports
            ;;
        metrics)
            show_metrics
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log ERROR "Неизвестная команда: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"
