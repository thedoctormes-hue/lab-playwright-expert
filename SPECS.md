# SPECS.md — Спецификации развития Playwright-экспертизы

**Дата:** 2026-05-17
**Каскад:** 8 агентов, 1.8 MB экспертизы
**Текущий уровень:** 42/100 → Цель: 75/100 за 2-3 недели

---

## Спек 1: Stealth Evolution (P0 — 1-2 дня)

**Цель:** Поднять покрытие антидетекта с 35% до 70%+

**P0 Векторы (критические — проверяют все антибот-системы):**

- navigator.vendor — маскировка под Google Inc.
- chrome.csi + chrome.loadTimes — фейк Chrome-specific APIs
- navigator.hardwareConcurrency — фейк под реальные значения (4-16)
- window.outerWidth/outerHeight — фейк под реальный viewport
- navigator.deviceMemory — маскировка под 8GB+
- screen.colorDepth / pixelDepth — фейк под 24/32 bit
- User-Agent Client Hints (Sec-CH-UA-*) — согласованные заголовки
- WebRTC IP leak — блокировка утечки реального IP

**P1 Векторы (важные — детект продвинутых систем):**

- AudioContext fingerprint — фейк под реальный Chrome
- navigator.connection — маскировка Network Information API
- navigator.getBattery — фейк под реальный уровень заряда
- navigator.mediaDevices — фейк списка устройств
- navigator.maxTouchPoints — корректное значение для платформы
- Intl API — фейк DateTimeFormat/NumberFormat
- SpeechSynthesis — фейк списка голосов
- PerformanceTiming — нормализация временных меток

**Архитектура интеграции:**

Каждый вектор = отдельный JS-скрипт в `stealth_scripts/` директории. `StealthConfig` загружает скрипты по уровню (basic/advanced/full). Новый класс `StealthBenchmark` — автоматический бенчмарк на bot.sannysoft.com, fingerprintjs.com, creepjs.com.

**Критерий готовности:** Проходит bot.sannysoft.com без красных маркеров, Cloudflare challenge решается автоматически.

---

## Спек 2: Security Hardening (P0 — 1 день)

**Цель:** Закрыть все критические уязвимости

**SSRF Protection для screenshot-service:**

- Валидация URL: блокировка file://, localhost, 127.0.0.1, 169.254.x.x, 10.x.x.x, 172.16-31.x.x, 192.168.x.x
- Только http/https протоколы
- Максимальный размер ответа: 10MB
- Таймаут: 30 секунд

**Аутентификация:**

- Bearer token через заголовок Authorization
- Rate limiting: 100 req/min на IP, 1000 req/min с токеном
- CORS whitelist: только домены лаборатории

**Изоляция:**

- Docker контейнер с --init и --ipc=host
- seccomp профиль для Chromium
- no-new-privileges: true
- read-only filesystem где возможно

**Секреты:**

- Cookies хранятся в зашифрованном виде (Fernet)
- API keys — только через environment variables
- Ротация секретов через secret_manager.py

**Аудит:**

- security_audit.py — ежедневная проверка конфигурации
- Алерт при обнаружении уязвимостей
- Логирование всех запросов в audit.log

---

## Спек 3: Architecture Evolution (P1 — 3-5 дней)

**Цель:** Превратить кит в устанавливаемый пакет с чистой архитектурой

**Новые модули:**

- metrics.py — сбор метрик (уже создан, нужна интеграция)
- proxy_rotation.py — автоматическая ротация прокси
- session_manager.py — управление сессиями и куками
- har_recorder.py — нативная HAR-запись через Playwright
- clock_control.py — манипуляция временем для тестов
- screencast.py — запись видео с аннотациями

**Улучшение существующих:**

- BrowserManager: добавить proxy rotation, HAR recording, screalth level
- ScreenshotMaker: добавить screencast, PDF с аннотациями, visual diff
- PageParser: добавить ARIA snapshot, self-healing локаторы
- StealthConfig: добавить уровни basic/advanced/full, бенчмарк
- LLMParser: добавить self-healing, кэширование, batch processing

**Установка как пакет:**

```bash
pip install "lab-playwright-expert @ file:///root/LabDoctorM/projects/lab-playwright-expert"
```

pyproject.toml с entry points, версионирование, зависимости.

**Конфигурация:**

- Профили: default, stealth, aggressive, minimal
- Пресеты: monitoring, scraping, crossposting, testing
- YAML-конфигурация с переопределением через env vars

---

## Спек 4: Metrics & Monitoring (P1 — 2-3 дня)

**Цель:** Полная наблюдаемость всех Playwright-компонентов

**Метрики (Prometheus-совместимые):**

- playwright_requests_total — количество запросов по типам
- playwright_request_duration_seconds — латентность
- playwright_errors_total — ошибки по типам
- stealth_score — текущий уровень маскировки
- browser_pool_size — размер пула браузеров
- cache_hit_ratio — эффективность кэша
- proxy_health — здоровье прокси

**Алерты:**

- Screenshot-service недоступен > 2 мин → Telegram
- Stealth score < 50% → Telegram
- Error rate > 5% → Telegram
- Proxy pool < 20% здоровых → Telegram
- Disk usage > 80% → Telegram

**Дашборд:**

- Telegram-бот с текстовым дашбордом (каждые 6 часов)
- /status — текущее состояние всех сервисов
- /metrics — ключевые метрики
- /stealth — текущий stealth score

**Stealth Tracker:**

- Ежедневный бенчмарк на bot.sannysoft.com
- История stealth score за 30 дней
- Алерт при падении score

---

## Спек 5: CI/CD & Automation (P1 — 2-3 дня)

**Цель:** Полностью автоматизированный pipeline без GitHub Actions

**Git hooks:**

- pre-commit: ruff lint + format check
- pre-push: lint + все тесты + health check
- post-merge: авто-деплой на main

**Автоматические тесты:**

- Unit-тесты: при каждом commit (быстро, без браузера)
- Полный прогон: каждые 6 часов через systemd timer
- E2E-тесты: перед каждым push в main

**Автоматический деплой:**

- При merge в main → тесты → restart сервисов
- Rollback при падении health check
- Логирование всех деплоев в /var/log/playwright-deploy.log

**Ротация кук:**

- Еженедельное обновление cookies для всех площадок
- Автоматическая проверка валидности
- Алерт при истечении сессии

---

## Спек 6: Integration with Lab Projects (P2 — 3-5 дней)

**Цель:** Подключить Playwright ко всем проектам лаборатории

**СнабЛаб:**

- Парсинг госзакупок (zakupki.gov.ru) — фоновая задача
- Мониторинг цен конкурентов — ежедневный скрипт
- E2E тестирование после каждого деплоя
- Подключение: pip install + sys.path

**Hype Pilot:**

- Кросспостинг на Habr/VC.ru — расширение crosspost.py
- Парсинг статистики публикаций — еженедельно
- LLM-адаптация к изменениям дизайна площадок
- Подключение: pip install + .env с куками

**Котолизатор VPN:**

- Мониторинг веб-интерфейсов VPN-панелей
- Проверка доступности из разных стран (прокси)
- Скриншоты дашбордов для отчётов
- Подключение: отдельный скрипт с BrowserManager

**Myrmex Control:**

- E2E тестирование критических сценариев
- Visual regression после каждого деплоя
- Подключение: playwright.config.ts в проекте

**Ворон:**

- Мониторинг новых AI-инструментов и фреймворков
- Парсинг changelog-ов и сравнение цен
- LLM-суммаризация для отчётов
- Подключение: отдельный скрипт с LLMParser

**Единая точка управления:**

- Центральный скрипт `lab_playwright_kit/orchestrator.py`
- Запуск всех задач по расписанию
- Единый лог и метрики
- Единый конфиг для всех проектов

---

## Спек 7: New Capabilities (P2 — 5-7 дней)

**Цель:** Внедрить новые возможности Playwright для конкурентного преимущества

**Screencast API:**

- Запись видео с аннотациями действий
- Покадровый захват для отчётов
- Демонстрации для ЗавЛаба
- Интеграция с ScreenshotMaker

**Playwright + LLM:**

- Self-healing локаторы (LLM находит новые селекторы при изменениях)
- Умный кросспостинг (LLM анализирует DOM и находит элементы)
- Playwright Test Agents (Planner/Generator/Healer)
- Интеграция с OpenRouter API

**Playwright + Proxy:**

- Автоматическая ротация при блокировке
- Health-check прокси
- Residential proxy для кросспостинга
- Геотаргетинг для мониторинга

**Playwright + Docker:**

- Официальный образ как base
- noVNC для визуальной отладки
- browserType.connectOverCDP() для подключения
- Kubernetes для масштабирования

**ARIA Snapshot Testing:**

- Тестирование структуры через accessibility tree
- YAML-файлы для каждого сайта
- Автоматическое обновление

**Clock API:**

- Тестирование таймаутов без реального ожидания
- Симуляция длительных периодов
- Детерминированное тестирование времени

---

## Спек 8: Use Cases Implementation (P2 — 5-7 дней)

**Цель:** Реализовать приоритетные кейсы из 15 предложенных

**Высокий приоритет (реализовать первыми):**

1. Мониторинг доступности сервисов — расширить site_monitor.py
2. Кросспостинг Hype Pilot — довести crosspost.py до production
3. Парсинг госзакупок — интегрировать с СнабЛабом
4. E2E тестирование Myrmex Control — запустить 14 тестов
5. Screenshot-as-a-Service — развёрнуть в production

**Средний приоритет:**

6. Мониторинг VPN-серверов — скрипт с прокси
7. Сбор данных для Ворона — LLM-парсинг
8. Парсинг цен конкурентов — интеграция с СнабЛабом
9. Тестирование форм авторизации — добавить в мониторинг
10. Мониторинг SSL — еженедельная проверка

**Низкий приоритет:**

11. PDF-отчёты из дашбордов — еженедельная генерация
12. Мониторинг социальных сетей — ежедневный сбор
13. Архивирование веб-страниц — ежемечная задача
14. Генерация документации — автоматизация
15. Мониторинг конкурентов — еженедельный отчёт

---

## Дорожная карта

**Неделя 1 (P0):**
- Stealth P0 векторы → 70% покрытие
- Security hardening → все уязвимости закрыты
- Итого: 42 → 55 баллов

**Неделя 2 (P1):**
- Architecture → пакет + новые модули
- Metrics → полная наблюдаемость
- CI/CD → автоматический pipeline
- Итого: 55 → 70 баллов

**Неделя 3 (P2):**
- Integration → все проекты подключены
- New Capabilities → screencast, LLM, proxy
- Use Cases → 5 высокоприоритетных кейсов
- Итого: 70 → 80+ баллов

---

## Критерии успеха

- Stealth score > 70% (сейчас 35%)
- 0 критических уязвимостей (сейчас 3)
- Все сервисы мониторятся (сейчас 0)
- CI/CD работает автоматически (сейчас нет)
- 5+ проектов лаборатории используют кит (сейчас 1)
- 10+ автоматизированных кейсов в production (сейчас 2)
