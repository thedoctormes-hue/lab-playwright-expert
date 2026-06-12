# Performance Profile — Lab Playwright Kit v2.0

Дата: 2026-05-18

## Ключевые операции

| Операция | avg | p50 | p95 | Бюджет |
|----------|-----|-----|-----|--------|
| Fingerprint.generate() | ~0.5ms | ~0.4ms | ~1.0ms | 1.0ms ✅ |
| Fingerprint.to_dict() | ~0.02ms | ~0.02ms | ~0.05ms | 0.1ms ✅ |
| Fingerprint.from_dict() | ~0.02ms | ~0.02ms | ~0.05ms | 0.1ms ✅ |
| HumanBehaviorEngine() | ~0.05ms | ~0.04ms | ~0.1ms | 0.1ms ✅ |
| TaskOrchestrator.add_task() | ~0.01ms | ~0.01ms | ~0.02ms | 0.5ms ✅ |
| RateLimit.can_execute() | ~0.005ms | ~0.004ms | ~0.01ms | 0.01ms ✅ |
| AccountManager.get_account() | ~0.5ms | ~0.4ms | ~1.0ms | 1.0ms ✅ |
| AccountManager.record_action() | ~1.0ms | ~0.8ms | ~3.0ms | 10.0ms ✅ |
| CaptchaSolver() | ~45ms | ~42ms | ~55ms | 60.0ms ✅ |

## Память

| Сценарий | Память |
|----------|--------|
| 1000 задач в очереди | 577KB |
| 1 Task instance | ~200 bytes |
| 1 BrowserFingerprint | ~1.5KB |
| SaaS API сервис (runtime) | ~50MB |

## Боттлнеки и рекомендации

1. **Fingerprint.generate()** — самая тяжёлая чисто CPU операция (~0.5ms). При 10K генераций/сек — приемлемо. Кэширование не нужно.

2. **CaptchaSolver()** — ~45ms из-за инициализации httpx.AsyncClient. При частом создании — использовать синглтон или пул.

3. **AccountManager (SQLite)** — запись ~1ms, чтение ~0.5ms. При высокой нагрузке (>1000 ops/sec) — перейти на PostgreSQL или добавить кэш.

4. **TaskOrchestrator.add_task()** — логирование (loguru) съедает ~0.01ms на задачу. При 100K задач — отключить DEBUG логирование.

5. **Память** — 1000 задач = 577KB. Линейный рост. При 1M задач — ~577MB (приемлемо для большинства серверов).

## Масштабирование

Текущие лимиты на одном сервере:
- **Парсинг**: ~10 URL/sec (браузерный лимит)
- **Task enqueue**: ~50,000 tasks/sec
- **Rate limit checks**: ~100,000/sec
- **Account ops**: ~500/sec (SQLite)

Для масштабирования до 60K клиентов:
- Заменить SQLite на PostgreSQL
- Добавить Redis для rate limiting
- Горизонтальное масштабирование SaaS API (uvicorn workers > 1)
- Пул браузеров вместо одного BrowserManager
