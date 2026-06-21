---
description: "lab-playwright-expert — история изменений"
type: changelog
last_reviewed: 2026-06-21
last_code_change: 2026-06-21
status: active
---

# Changelog

## v2.1.0 — 2026-06-12

### Evolution Layer — WorkflowRunner + StealthAudit + CloudflareBypass

**Новые модули:**
- `workflow_runner.py` — мост между task_template (BaseTask) и task_orchestrator (TaskOrchestrator)
  - `register_task_type()` + `add_work()` + `run()`
  - `WorkItem`, `WorkflowResult`
  - Handler: execute → run → crosspost fallback
  - Безопасный `__name__` для task_class через `getattr(..., str())`
- `stealth_audit.py` — единый аудит скрытности
  - `StealthAuditReport`: score + benchmark + pipeline в один отчёт
  - `run_full()` / `run_score()` / `run_benchmark()` / `run_pipeline()`
  - `overall_score`: взвешенный (score 40% + benchmark 60%)
  - `weak_points`, `recommendations`, `summary`, `to_dict()`
  - Graceful failure: score/pipeline/benchmark fail → warning, не crash
- `cloudflare_bypass.py` — обход Cloudflare challenge через FlareSolverr
  - `FlareSolverrClient`: health_check, solve, solve_post, retry
  - `BypassResult` dataclass
  - Exponential backoff retry (2^attempt)
  - Fallback: FlareSolverr → direct request

**Исправления:**
- CloudflareBypass: `await asyncio.sleep()` при HTTP error перед `continue` (retry backoff)

**Тестирование:**
- 76 новых тестов (CloudflareBypass 18 + WorkflowRunner 19 + StealthAudit 39)
- 100% покрытие новых модулей

---

## v1.0.0 — 2026-05-17

### Полный релиз

**Новые модули:**
- `stealth_webrtc.py` — WebRTC IP leak protection (3 режима: block_all, filter_host, fake_ice)
- `stealth_audio.py` — AudioContext fingerprint spoofing (Mulberry32 PRNG)
- `stealth_client_hints.py` — User-Agent Client Hints spoofing
- `stealth_benchmark.py` — Автоматический бенчмарк stealth (bot.sannysoft.com)
- `proxy_rotation.py` — Ротация прокси (round_robin, random, weighted)
- `session_manager.py` — Управление сессиями с Fernet шифрованием
- `har_recorder.py` — Запись HAR с фильтрацией и статистикой

**Stealth система:**
- 16 скриптов антидетекта (было 6)
- 4 уровня: minimal (1), standard (6), advanced (16), full (16 + random UA)
- WebRTC, AudioContext, Client Hints

**Тестирование:**
- 300 тестов (было 96)
- Покрытие всех новых модулей
- Интеграционные тесты с реальным браузером

**CI/CD:**
- `.github/workflows/ci.yml` — lint + test (Python 3.10-3.12)
- `.github/workflows/security.yml` — bandit + safety
- `.github/workflows/release.yml` — build + docker

**Документация:**
- ARCHITECTURE.md — полная архитектура
- API.md — API reference
- GUIDES.md — руководства
- DEPLOY.md — деплой
- ADR — Architecture Decision Records

**Исправления:**
- Pydantic v1 → v2 миграция (`@validator` → `@field_validator`)
- FastAPI `on_event` → `lifespan` async context manager
- Порядок проверки платформ в `_parse_user_agent` (Android/iOS → Linux/macOS)

---

## v0.3.0 — 2026-05-16

### Security + Screenshot Service

- Screenshot-as-a-Service (FastAPI)
- Bearer token аутентификация
- SSRF защита
- Rate limiting
- Security headers
- 38 security тестов

---

## v0.2.0 — 2026-05-16

### Core + New Capabilities

- BrowserManager, StealthConfig, ScreenshotMaker
- PageParser, NetworkInterceptor
- ScreencastRecorder, ARIASnapshot, ClockController
- 96 тестов

---

## v0.1.0 — 2026-05-15

### Initial Scaffold

- Структура проекта
- pyproject.toml
- Базовые модули
