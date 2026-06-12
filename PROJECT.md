---
name: Lab Playwright Expert
type: framework
status: active
owner: ant
priority: medium
stack: [Python, Playwright, Docker]
version: "2.0.0"
path: projects/lab-playwright-expert
created: "2026-05-10"
---

# Lab Playwright Expert

Продвинутый фреймворк для автоматизации браузера на базе Playwright. v2.0.

## Владелец
Муравей (ant)

## Структура
- `config/` — конфигурация
- `docs/` — документация
- `benchmark_reports/` — отчёты бенчмарков
- Docker: `docker-compose.yml`, `Dockerfile`, `Dockerfile.secure`
- `.pre-commit-config.yaml` — pre-commit хуки
- `.github/` — GitHub Actions

## Документация
- [README.md](README.md) — описание
- [CHANGELOG.md](CHANGELOG.md) — история изменений
- [Makefile](Makefile) — команды сборки и тестирования
