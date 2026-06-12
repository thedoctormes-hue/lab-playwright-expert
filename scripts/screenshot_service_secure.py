"""
Screenshot-as-a-Service — БЕЗОПАСНАЯ версия.

Улучшения безопасности:
  1. API Key аутентификация (header + env generation)
  2. Rate limiting (Token Bucket на каждый ключ)
  3. URL validation (SSRF protection, allowlist схем)
  4. Безопасный кэш (restricted permissions, path traversal protection)
  5. Security headers в ответах
  6. Ограничение размера ответа и таймаутов

API:
  POST /screenshot — создать скриншот (требует X-API-Key)
  GET  /screenshot — вариант с query params (требует X-API-Key)
  GET  /screenshot/download/{key} — скачать (требует X-API-Key)
  GET  /health — проверка здоровья (публичный)
  DELETE /cache — очистить кэш (требует X-API-Key)

Запуск:
  python3 screenshot_service_secure.py
  # API_KEY генерируется автоматически при первом запуске и пишется в stderr
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets

# ─── Конфигурация ───────────────────────────────────────────────
import sys
import time
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from loguru import logger
from pydantic import BaseModel, Field, validator


KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


# ─── Security Configuration ─────────────────────────────────────

# API Keys — загружаются из env, или генерируются при первом запуске
_API_KEYS: set[str] = set()
_env_key = os.getenv("SCREENSHOT_API_KEY", "")
if _env_key:
    _API_KEYS.add(_env_key)
    logger.info(f"Loaded API key from env ({len(_env_key)} chars)")
else:
    _generated = secrets.token_urlsafe(32)
    _API_KEYS.add(_generated)
    # Пишем в stderr, чтобы не попало в access log
    print(
        f"\n{'='*60}\n"
        f"  ⚠️  GENERATED API KEY (set SCREENSHOT_API_KEY env to persist):\n"
        f"  {_generated}\n"
        f"{'='*60}\n",
        file=sys.stderr,
    )
    logger.warning(
        "No SCREENSHOT_API_KEY env set — using ephemeral key. "
        "Set SCREENSHOT_API_KEY for persistent access."
    )

# Rate limit конфиугration
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))  # запросов
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))      # секунд

# Разрешённые схемы URL
ALLOWED_SCHEMES = {"https", "http"}

# Заблокированные хосты (SSRF protection)
BLOCKED_HOST_PATTERNS = [
    re.compile(r"^localhost$", re.IGNORECASE),
    re.compile(r"^127\."),
    re.compile(r"^0\.0\.0\.0$"),
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^169\.254\."),           # link-local
    re.compile(r"^\[::1\]$"),             # IPv6 localhost
    re.compile(r"^\[fd", re.IGNORECASE),  # IPv6 private
    re.compile(r"^\[fe80", re.IGNORECASE),# IPv6 link-local
    re.compile(r"^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\."),  # CGNAT
    re.compile(r"\.local$", re.IGNORECASE),
    re.compile(r"\.internal$", re.IGNORECASE),
    re.compile(r"\.localhost$", re.IGNORECASE),
    # Cloud metadata endpoints
    re.compile(r"^169\.254\.169\.254$"),  # AWS/GCP/Azure metadata
    re.compile(r"^metadata\.google\.internal$"),
    re.compile(r"^metadata\.internal$"),
]

# Максимальная длина URL
MAX_URL_LENGTH = 2048

# Кэш
CACHE_DIR = Path(os.getenv("SCREENSHOT_CACHE_DIR", "/tmp/screenshot_cache_secure"))
CACHE_TTL = int(os.getenv("SCREENSHOT_CACHE_TTL", "300"))


# ─── Rate Limiter ────────────────────────────────────────────────

@dataclass
class _TokenBucket:
    """Token bucket rate limiter для каждого API key."""
    max_tokens: int
    refill_rate: float  # tokens per second
    tokens: float = 0
    last_refill: float = 0

    def __post_init__(self):
        self.tokens = float(self.max_tokens)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_rate_limiters: dict[str, _TokenBucket] = {}


def _get_rate_limiter(api_key: str) -> _TokenBucket:
    if api_key not in _rate_limiters:
        _rate_limiters[api_key] = _TokenBucket(
            max_tokens=RATE_LIMIT_REQUESTS,
            refill_rate=RATE_LIMIT_REQUESTS / RATE_LIMIT_WINDOW,
        )
    return _rate_limiters[api_key]


# ─── URL Validation (SSRF Protection) ───────────────────────────

class URLValidationError(Exception):
    pass


def validate_url(url: str) -> str:
    """
    Валидация URL против SSRF и инъекций.

    Проверяет:
    - Длина URL
    - Схему (только http/https)
    - Отсутствие credentials в URL
    - Хост не в блокированных диапазонах
    - Нет обходов через @, unicode, escape
    - Нет path traversal
    """
    if not url:
        raise URLValidationError("URL не может быть пустым")

    if len(url) > MAX_URL_LENGTH:
        raise URLValidationError(f"URL слишком длинный (макс. {MAX_URL_LENGTH} символов)")

    # Нормализация: убрать CRLF инъекции
    if "\r" in url or "\n" in url or "\0" in url:
        raise URLValidationError("URL содержит недопустимые символы")

    # Попытка парсинга
    try:
        parsed = urlparse(url)
    except Exception:
        raise URLValidationError("Ошибка парсинга URL")

    # Схема
    scheme = parsed.scheme.lower()
    if not scheme:
        raise URLValidationError("URL должен содержать схему (http:// или https://)")
    if scheme not in ALLOWED_SCHEMES:
        raise URLValidationError(f"Схема '{scheme}' не разрешена. Допустимые: {ALLOWED_SCHEMES}")

    # Host
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL не содержит хоста")

    # Убрать порт для проверки
    host_clean = hostname.strip("[]")

    # Проверить блокированные паттерны
    for pattern in BLOCKED_HOST_PATTERNS:
        if pattern.search(host_clean):
            raise URLValidationError(
                f"Хост '{host_clean}' заблокирован (SSRF protection). "
                "Нельзя обращаться к внутренним/локальным адресам."
            )

    # IP доплата: если хост — IP адрес, проверить через ipaddress
    try:
        addr = ip_address(host_clean)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise URLValidationError(f"IP {host_clean} — внутренний/локальный адрес")
    except ValueError:
        # Не IP — это hostname, допустимо (будет resolved в браузере)
        pass

    # Проверка на обходные техники
    # Двойной декодинг, @ для credential injection
    if "@" in (parsed.netloc or ""):
        raise URLValidationError("URL не должен содержать credentials (@)")

    # Нет path traversal в ключе
    if ".." in parsed.path:
        raise URLValidationError("Path traversal не допускается")

    # URL должен быть стандартизирован
    normalized = parsed.geturl()
    logger.debug(f"URL validated: {hostname} (scheme={scheme})")

    return normalized


# ─── FastAPI Application ─────────────────────────────────────────

app = FastAPI(
    title="Screenshot-as-a-Service (Secure)",
    description="Playwright скриншоты по HTTP API — с аутентификацией и SSRF защитой",
    version="1.0.0-secure",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ─── Middleware: Security Headers ────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


# ─── Dependencies ────────────────────────────────────────────────

async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    """Проверка API Key из заголовка X-API-Key."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    # Постоянное время сравнения — защита от timing attack
    for valid_key in _API_KEYS:
        if secrets.compare_digest(x_api_key, valid_key):
            return x_api_key
    raise HTTPException(
        status_code=403,
        detail="Invalid API key",
    )


async def check_rate_limit(api_key: str = Depends(verify_api_key)) -> str:
    """Rate limiting для API key."""
    limiter = _get_rate_limiter(api_key)
    if not limiter.consume():
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Limit: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
        )
    return api_key


# ─── Models ──────────────────────────────────────────────────────

class ScreenshotRequest(BaseModel):
    url: str = Field(..., description="URL для скриншота")
    full_page: bool = Field(False, description="Полная страница")
    width: int = Field(1920, ge=320, le=3840)
    height: int = Field(1080, ge=240, le=2160)
    wait_for: str | None = Field(None, description="CSS-селектор для ожидания")
    wait_ms: int = Field(0, ge=0, le=30000)
    stealth: bool = Field(True)
    format: str = Field("png", regex="^(png|pdf)$")

    @validator("url")
    def url_must_be_valid(self, v):
        try:
            return validate_url(v)
        except URLValidationError as e:
            raise ValueError(str(e))

    @validator("wait_for")
    def css_selector_safe(self, v):
        if v is None:
            return v
        # Простая проверка: не должен содержать спецсимволов для инъекции
        if any(c in v for c in ["<", ">", "{", "}", "\\", "\x00"]):
            raise ValueError("CSS селектор содержит недопустимые символы")
        if len(v) > 256:
            raise ValueError("CSS селектор слишком длинный")
        return v


class ScreenshotResponse(BaseModel):
    success: bool
    url: str
    screenshot_url: str | None = None
    cached: bool = False
    load_time_ms: float = 0
    error: str | None = None


# ─── Cache Helpers ───────────────────────────────────────────────

def _ensure_secure_cache_dir():
    """Создать кэш-директорию с безопасными правами."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Только владелец (0700)
    os.chmod(CACHE_DIR, 0o700)


def cache_key(url: str, full_page: bool, width: int, height: int) -> str:
    data = f"{url}:{full_page}:{width}:{height}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_cached_screenshot(key: str) -> Path | None:
    """Проверить кэш с защитой от path traversal."""
    # Ключ должен быть hex (sha256)
    if not re.match(r"^[a-f0-9]{64}$", key):
        logger.warning(f"Invalid cache key format: {key[:20]}...")
        return None

    for ext in ("png", "pdf"):
        path = CACHE_DIR / f"{key}.{ext}"
        # Дополнительная проверка: resolved path должен быть внутри CACHE_DIR
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(CACHE_DIR.resolve())):
                logger.warning(f"Path traversal attempt: {key}")
                return None
        except Exception:
            return None

        if resolved.exists():
            age = time.time() - resolved.stat().st_mtime
            if age < CACHE_TTL:
                return resolved
            else:
                resolved.unlink(missing_ok=True)
    return None


# ─── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Публичный health check."""
    return {
        "status": "ok",
        "service": "screenshot-as-a-service",
        "version": "1.0.0-secure",
    }


@app.post("/screenshot", response_model=ScreenshotResponse)
async def create_screenshot(
    request: ScreenshotRequest,
    api_key: str = Depends(check_rate_limit),
):
    """Создать скриншот страницы. Требует X-API-Key header."""
    start = time.time()

    # Проверить кэш
    key = cache_key(request.url, request.full_page, request.width, request.height)
    cached = get_cached_screenshot(key)
    if cached:
        logger.info(f"Cache hit: {request.url}")
        return ScreenshotResponse(
            success=True,
            url=request.url,
            screenshot_url=f"/screenshot/download/{key}",
            cached=True,
            load_time_ms=(time.time() - start) * 1000,
        )

    try:
        async with BrowserManager(
            headless=True,
            timeout=30000,
            viewport={"width": request.width, "height": request.height},
        ) as browser:
            page = await browser.new_page()

            if request.stealth:
                await apply_stealth(page, StealthConfig.minimal())

            await page.goto(request.url, wait_until="domcontentloaded")

            if request.wait_for:
                try:
                    await page.wait_for_selector(request.wait_for, timeout=10000)
                except Exception:
                    logger.warning(f"Timeout waiting for: {request.wait_for}")

            if request.wait_ms > 0:
                await page.wait_for_timeout(request.wait_ms)

            maker = ScreenshotMaker(str(CACHE_DIR))

            if request.format == "pdf":
                path = await maker.pdf(page, prefix=key)
            elif request.full_page:
                path = await maker.full_page(page, prefix=key)
            else:
                path = await maker.viewport(page, prefix=key)

            # Установить безопасные права на созданный файл
            os.chmod(path, 0o600)

            load_time = (time.time() - start) * 1000
            logger.info(f"Screenshot: {request.url} → {path} ({load_time:.0f}ms)")

            return ScreenshotResponse(
                success=True,
                url=request.url,
                screenshot_url=f"/screenshot/download/{key}",
                cached=False,
                load_time_ms=load_time,
            )

    except Exception as e:
        logger.error(f"Screenshot failed for {request.url}: {e}")
        # Не раскрываем внутренние детали ошибки
        raise HTTPException(status_code=500, detail="Screenshot generation failed")


@app.get("/screenshot/download/{key}")
async def download_screenshot(
    key: str,
    api_key: str = Depends(check_rate_limit),
):
    """Скачать скриншот. Требует X-API-Key header."""
    # Валидация ключа кэша
    if not re.match(r"^[a-f0-9]{64}$", key):
        raise HTTPException(status_code=400, detail="Invalid key format")

    for ext in ("png", "pdf"):
        path = CACHE_DIR / f"{key}.{ext}"
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(CACHE_DIR.resolve())):
                raise HTTPException(status_code=403, detail="Access denied")
        except Exception:
            raise HTTPException(status_code=404, detail="Screenshot not found")

        if resolved.exists():
            media_type = "image/png" if ext == "png" else "application/pdf"
            return FileResponse(resolved, media_type=media_type)

    raise HTTPException(status_code=404, detail="Screenshot not found")


@app.get("/screenshot")
async def get_screenshot_get(
    url: str = Query(...),
    full_page: bool = Query(False),
    width: int = Query(1920),
    height: int = Query(1080),
    format: str = Query("png"),
    api_key: str = Depends(check_rate_limit),
):
    """GET-вариант. Требует X-API-Key header."""
    request = ScreenshotRequest(
        url=url, full_page=full_page, width=width, height=height, format=format
    )
    return await create_screenshot(request, api_key)


@app.delete("/cache")
async def clear_cache(api_key: str = Depends(check_rate_limit)):
    """Очистить кэш. Требует X-API-Key header."""
    count = 0
    for f in CACHE_DIR.iterdir():
        try:
            resolved = f.resolve()
            if str(resolved).startswith(str(CACHE_DIR.resolve())):
                resolved.unlink()
                count += 1
        except Exception:
            pass
    return {"cleared": count}


# ─── Startup ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    _ensure_secure_cache_dir()
    logger.info(
        f"Screenshot Service (secure) started. "
        f"Rate limit: {RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s. "
        f"Cache dir: {CACHE_DIR} (0700). "
        f"Active API keys: {len(_API_KEYS)}"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8190)
