---
description: "🎭 Передача сессии Lab Playwright Expert"
type: handoff
last_reviewed: 2026-05-27
status: active
---
# 🔄 SESSION HANDOFF — Lab Playwright Expert

**Дата:** 2026-05-27
**Статус:** 🟢 Активен
**Тип:** library/toolkit

## 📊 TL;DR
Фреймворк для веб-парсинга на базе Playwright. Универсальный инструмент для скрапинга с поддержкой stealth-режима, прокси, дедупликации и экспорта данных.

## Технологический стек
- Python 3.10-3.12, Playwright 1.59+
- Pydantic 2.0+, FastAPI (опционально)
- Docker, systemd
- Scrapy-подобная архитектура (spiders, middlewares, pipelines)

## Что работает ✅
- 300 тестов (unit + integration)
- Stealth middleware (обход защиты)
- Proxy middleware
- Dedup + validation + export pipelines
- Готовые spiders (generic, zakupki)
- Benchmark reports

## Структура
```
src/lab_playwright_kit/
  scrapy_engine/
    spiders/        # Пауки (generic, zakupki)
    middlewares/    # Stealth, proxy
    pipelines/      # Dedup, validation, export
    settings.py     # Конфигурация
tests/              # 300 тестов
config/             # Конфигурации
scripts/            # Утилиты
```

## ⚠️ Известные проблемы
- Активная разработка — API может меняться

## Открытые задачи
- Расширение библиотеки spiders
- Документация и примеры использования
- Интеграция с проектами (fedlab_parser, snablab)
