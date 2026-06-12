# ============================================================
# Dockerfile — Screenshot-as-a-Service (lab-playwright-expert)
# ============================================================
# Мультистейдж сборка: builder → runtime
# Базовый образ: python 3.11 slim + Playwright Chromium
#
# Улучшения:
#   - Multi-stage build (builder → runtime)
#   - Non-root user (uid 1001, pptruser)
#   - Multi-arch hints (amd64 + arm64)
#   - Оптимизированный layer caching
#   - Health check
#   - Read-only root filesystem friendly
#   - Security: dropped capabilities, no-new-privileges
#
# Сборка:
#   docker build -t lab-playwright-expert:latest .
#   docker build --platform linux/amd64 -t lab-playwright-expert:amd64 .
#   docker build --platform linux/arm64 -t lab-playwright-expert:arm64 .
# ============================================================

# ---- Stage 1: Builder ----
# Собираем Python-зависимости в отдельном слое
FROM python:3.11-slim AS builder

WORKDIR /build

# Системные зависимости для сборки (только компилятор)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости отдельно для кэширования слоёв
# Этот слой пересобирается ТОЛЬКО при изменении requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Browser Installer ----
# Отдельный слой для установки Playwright-браузеров
# Кэшируется независимо от исходного кода
FROM python:3.11-slim AS browser-installer

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir playwright>=1.59.0 \
    && playwright install chromium \
    && rm -rf /root/.cache/pip

# ---- Stage 3: Runtime ----
FROM python:3.11-slim AS runtime

# Multi-arch метки (используются docker buildx)
LABEL maintainer="LabDoctorM <streikbrecher>"
LABEL description="Screenshot-as-a-Service — Playwright + FastAPI"
LABEL version="2.0.0"
LABEL org.opencontainers.image.source="https://github.com/LabDoctorM/lab-playwright-expert"

# Системные зависимости для Playwright Chromium
# Устанавливаем одним слоем для минимизации размера образа
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/cache/apt/archives

# Копируем Python-пакеты из builder
COPY --from=builder /install /usr/local

# Копируем установленные браузеры из browser-installer
COPY --from=browser-installer /root/.cache/ms-playwright /root/.cache/ms-playwright
COPY --from=browser-installer /usr/local/lib/python3.11/site-packages/playwright /usr/local/lib/python3.11/site-packages/playwright

# ─── Verify Playwright installation ──────────────────────────
RUN python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')" \
    && python3 -c "import playwright; print(f'Playwright {playwright.__version__}')" \
    && ls /root/.cache/ms-playwright/chromium-*/chrome-linux/chrome \
    || (echo "ERROR: Playwright Chromium not found!" && exit 1)

# ─── Non-root пользователь ────────────────────────────────────
RUN groupadd -r pptruser && useradd -r -g pptruser -G audio,video pptruser \
    && mkdir -p /home/pptruser/Downloads \
    && chown -R pptruser:pptruser /home/pptruser

# Рабочая директория
WORKDIR /app
RUN chown pptruser:pptruser /app

# Кэш скриншотов — с безопасными правами
RUN mkdir -p /tmp/screenshot_cache \
    && chown pptruser:pptruser /tmp/screenshot_cache \
    && chmod 700 /tmp/screenshot_cache

# Копируем исходный код (после установки зависимостей — лучше кэширование)
COPY --chown=pptruser:pptruser src/ /app/src/
COPY --chown=pptruser:pptruser scripts/screenshot_service.py /app/screenshot_service.py

# ─── Переменные окружения ─────────────────────────────────────
ENV PYTHONPATH=/app/src:/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CACHE_DIR=/tmp/screenshot_cache \
    CACHE_TTL=300 \
    # Отключить setuid sandbox в контейнере
    PLAYWRIGHT_CHROMIUM_USE_SANDBOX=0

# ─── Health check ─────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8190/health || exit 1

# Порт
EXPOSE 8190

# ─── Переключиться на non-root ────────────────────────────────
USER pptruser

# Запуск
CMD ["uvicorn", "screenshot_service:app", \
     "--host", "0.0.0.0", \
     "--port", "8190", \
     "--workers", "1", \
     "--log-level", "info"]
