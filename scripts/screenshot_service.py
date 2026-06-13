"""
Screenshot-as-a-Service — FastAPI микросервис для создания скриншотов.

Безопасность:
  - Bearer token аутентификация (Authorization header / env SCREENSHOT_SERVICE_TOKEN)
  - SSRF protection: блокировка file://, ftp://, data://, javascript:, внутренних IP
  - Rate limiting: 100 req/min (anonymous) / 1000 req/min (authenticated)
  - URL validation: длина, схема, хост, path traversal
  - Security headers: X-Content-Type-Options, X-Frame-Options, CSP, HSTS
  - Безопасный кэш: 0700 permissions, path traversal protection, SHA-256 ключи
  - Логирование всех запросов с IP клиента

API:
  POST /screenshot              — создать скриншот (auth optional, rate limit зависит)
  GET  /screenshot              — GET-вариант (auth optional)
  GET  /screenshot/download/{key} — скачать скриншот (auth optional)
  DELETE /cache                 — очистить кэш (auth optional)
  GET  /health                  — проверка здоровья (публичный)
  GET  /metrics                 — Prometheus-метрики (публичный)

Запуск:
  export SCREENSHOT_SERVICE_TOKEN="your-secret-token"
  uvicorn screenshot_service:app --host 0.0.0.0 --port 8190
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import socket
import sys
import time
from dataclasses import dataclass
from ipaddress import ip_address as parse_ip_address
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field, field_validator


# ─── Пути и импорты ──────────────────────────────────────────────
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))

from lab_playwright_kit.browser import BrowserManager
from lab_playwright_kit.screenshot import ScreenshotMaker
from lab_playwright_kit.stealth import StealthConfig, apply_stealth


# Metrics — опциональный модуль (prometheus_client может быть не установлен)
try:
    from lab_playwright_kit.metrics import (
        SS_ACTIVE_BROWSERS,
        SS_BROWSER_ERRORS,
        SS_LATENCY,
        SS_REQUESTS,
        CacheMetrics,
        LatencyTimer,
        get_metrics_output,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False
    # Заглушки для работы без prometheus_client

    class _NoOpMetric:
        def labels(self, *a, **kw): return self
        def inc(self, *a, **kw): pass
        def dec(self, *a, **kw): pass
        def set(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def time(self): return _NullContext()

    class _NullContext:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    SS_REQUESTS = _NoOpMetric()
    SS_LATENCY = _NoOpMetric()
    SS_ACTIVE_BROWSERS = _NoOpMetric()
    SS_BROWSER_ERRORS = _NoOpMetric()

    class CacheMetrics:
        def __init__(self): self.hits = _NoOpMetric(); self.misses = _NoOpMetric()

    def LatencyTimer(*a, **kw):
        return _NullContext()

    def get_metrics_output(): return b""

# ═══════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ БЕЗОПАСНОСТИ
# ═══════════════════════════════════════════════════════════════════

# --- Bearer Token (обязателен) ---
_SERVICE_TOKEN: str | None = os.getenv("SCREENSHOT_SERVICE_TOKEN")
if not _SERVICE_TOKEN:
    logger.critical(
        "SCREENSHOT_SERVICE_TOKEN env var is not set! "
        "Service will not start without a token. "
        "Generate one: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
    sys.exit(1)

if len(_SERVICE_TOKEN) < 16:
    logger.critical("SCREENSHOT_SERVICE_TOKEN must be at least 16 characters long")
    sys.exit(1)

logger.info(f"Auth configured: Bearer token loaded ({len(_SERVICE_TOKEN)} chars)")

# --- Rate Limiting ---
RATE_LIMIT_ANONYMOUS = int(os.getenv("RATE_LIMIT_ANONYMOUS", "100"))
RATE_LIMIT_AUTHENTICATED = int(os.getenv("RATE_LIMIT_AUTHENTICATED", "1000"))
RATE_LIMIT_WINDOW = 60

# --- URL Validation ---
ALLOWED_SCHEMES = {"http", "https"}
MAX_URL_LENGTH = 2048

# Сети для блокировки (SSRF)
_BLOCKED_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
    ip_network("0.0.0.0/8"),
    ip_network("100.64.0.0/10"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
    ip_network("::1/128"),
]

# Регулярные выражения для блокировки хостов
_BLOCKED_HOST_PATTERNS = [
    re.compile(r"^localhost$", re.IGNORECASE),
    re.compile(r"\.local$", re.IGNORECASE),
    re.compile(r"\.localhost$", re.IGNORECASE),
    re.compile(r"\.internal$", re.IGNORECASE),
    re.compile(r"^metadata\.google\.internal$", re.IGNORECASE),
    re.compile(r"^metadata\.internal$", re.IGNORECASE),
    re.compile(r"^169\.254\.169\.254$"),
]

# --- Cache ---
CACHE_DIR = Path(os.getenv("SCREENSHOT_CACHE_DIR", "/tmp/screenshot_cache"))
CACHE_TTL = int(os.getenv("SCREENSHOT_CACHE_TTL", "300"))

# --- Viewport limits ---
MIN_VIEWPORT_WIDTH = 320
MAX_VIEWPORT_WIDTH = 3840
MIN_VIEWPORT_HEIGHT = 240
MAX_VIEWPORT_HEIGHT = 2160
MAX_WAIT_MS = 30000
NAVIGATION_TIMEOUT_MS = 30000


# ═══════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════

@dataclass
class _TokenBucket:
    """Token bucket rate limiter по клиенту (IP или токен)."""
    max_tokens: int
    refill_rate: float
    tokens: float = 0.0
    last_refill: float = 0.0

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
_rate_limiters_last_access: dict[str, float] = {}
RATE_LIMITER_TTL = 3600


def _cleanup_rate_limiters():
    """Remove stale rate limiters that haven't been accessed within TTL."""
    now = time.monotonic()
    stale = [cid for cid, last in _rate_limiters_last_access.items() if now - last > RATE_LIMITER_TTL]
    for cid in stale:
        del _rate_limiters[cid]
        del _rate_limiters_last_access[cid]
    if stale:
        logger.debug(f'Cleaned up {len(stale)} stale rate limiters')


_MAX_RATE_LIMITERS = 10000


def _get_rate_limiter(client_id: str, authenticated: bool) -> _TokenBucket:
    if client_id not in _rate_limiters:
        # Evict stale entries when map grows too large
        if len(_rate_limiters) >= _MAX_RATE_LIMITERS:
            _cleanup_rate_limiters()
        limit = RATE_LIMIT_AUTHENTICATED if authenticated else RATE_LIMIT_ANONYMOUS
        _rate_limiters[client_id] = _TokenBucket(
            max_tokens=limit,
            refill_rate=limit / RATE_LIMIT_WINDOW,
        )
    _rate_limiters_last_access[client_id] = time.monotonic()
    return _rate_limiters[client_id]


# ═══════════════════════════════════════════════════════════════════
# SSRF PROTECTION — URL VALIDATION
# ═══════════════════════════════════════════════════════════════════

class URLValidationError(Exception):
    pass


def validate_url(url: str) -> str:
    """
    Полная валидация URL против SSRF и инъекций.

    Проверяет:
    - Длина URL (макс. 2048)
    - Схема (только http/https)
    - CRLF / null-byte инъекции
    - Credentials в URL (@)
    - Path traversal (..)
    - Блокированные хосты (localhost, .local, .internal)
    - Внутренние/частные IP через ipaddress
    - Cloud metadata endpoints
    - DNS Rebinding: резолвит DNS и проверяет все resolved IP

    Возвращает нормализованный URL или бросает URLValidationError.
    """
    if not url or not url.strip():
        raise URLValidationError("URL не может быть пустым")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise URLValidationError(
            f"URL слишком длинный: {len(url)} символов (макс. {MAX_URL_LENGTH})"
        )

    # CRLF / null-byte инъекции
    if any(c in url for c in ("\r", "\n", "\0")):
        raise URLValidationError("URL содержит недопустимые символы (CRLF/null)")

    # Парсинг
    try:
        parsed = urlparse(url)
    except Exception:
        raise URLValidationError("Ошибка парсинга URL")

    # Схема
    scheme = parsed.scheme.lower()
    if not scheme:
        raise URLValidationError("URL должен содержать схему (http:// или https://)")
    if scheme not in ALLOWED_SCHEMES:
        raise URLValidationError(
            f"Схема '{scheme}' не разрешена. Допустимые: {', '.join(sorted(ALLOWED_SCHEMES))}"
        )

    # Хост
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL не содержит хоста")

    host_lower = hostname.lower().strip("[]")

    # Проверка regex-паттернов
    for pattern in _BLOCKED_HOST_PATTERNS:
        if pattern.search(host_lower):
            raise URLValidationError(
                f"Хост '{host_lower}' заблокирован (SSRF protection)"
            )

    # Проверка IP через ipaddress
    try:
        addr = parse_ip_address(host_lower)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise URLValidationError(
                    f"IP {host_lower} находится в заблокированной сети {network}"
                )
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise URLValidationError(
                f"IP {host_lower} — внутренний/локальный адрес"
            )
    except ValueError:
        # Не IP — это hostname. Резолвим DNS и проверяем IP (защита от DNS Rebinding).
        try:
            try:
                port = parsed.port or (443 if scheme == "https" else 80)
            except ValueError:
                raise URLValidationError(f"Невалидный порт в URL: {url}")
            resolved = socket.getaddrinfo(host_lower, port)
            for family, type_, proto, canonname, sockaddr in resolved:
                addr = parse_ip_address(sockaddr[0])
                for network in _BLOCKED_NETWORKS:
                    if addr in network:
                        raise URLValidationError(
                            f"DNS rebinding detected: {host_lower} resolves to "
                            f"blocked IP {addr} in {network}"
                        )
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    raise URLValidationError(
                        f"DNS rebinding detected: {host_lower} resolves to "
                        f"internal IP {addr}"
                    )
        except socket.gaierror:
            raise URLValidationError(f"DNS resolution failed for host: {host_lower}")

    # Credentials в netloc (user:pass@host)
    if "@" in (parsed.netloc or ""):
        raise URLValidationError("URL не должен содержать credentials (@)")

    # Path traversal
    if ".." in (parsed.path or ""):
        raise URLValidationError("Path traversal (..) не допускается")

    # Порт (обёрнуто в try/except т.к. urlparse бросает ValueError для порта > 65535)
    try:
        port = parsed.port
    except ValueError:
        raise URLValidationError("Недопустимый порт в URL")
    if port is not None:
        if port < 1 or port > 65535:
            raise URLValidationError(f"Недопустимый порт: {port}")

    normalized = parsed.geturl()
    logger.debug(f"URL validated OK: {host_lower} (scheme={scheme})")
    return normalized


# ═══════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _ensure_secure_cache_dir()
    logger.info(
        f"╔══════════════════════════════════════════════════\n"
        f"║  Screenshot-as-a-Service v1.0.0-secure started  \n"
        f"╠══════════════════════════════════════════════════\n"
        f"║  Auth:       Bearer token (required to start)   \n"
        f"║  Rate limit: {RATE_LIMIT_ANONYMOUS}/{RATE_LIMIT_WINDOW}s (anon) / "
        f"{RATE_LIMIT_AUTHENTICATED}/{RATE_LIMIT_WINDOW}s (auth)\n"
        f"║  Cache:      {CACHE_DIR} (0700, TTL={CACHE_TTL}s)\n"
        f"║  Viewport:   {MIN_VIEWPORT_WIDTH}x{MIN_VIEWPORT_HEIGHT} — "
        f"{MAX_VIEWPORT_WIDTH}x{MAX_VIEWPORT_HEIGHT}\n"
        f"║  Timeout:    {NAVIGATION_TIMEOUT_MS}ms navigation\n"
        f"╚══════════════════════════════════════════════════"
    )
    yield

app = FastAPI(
    title="Screenshot-as-a-Service",
    description="Playwright скриншоты по HTTP API с SSRF-защитой и аутентификацией",
    version="1.0.0-secure",
    lifespan=_lifespan,
)

cache_metrics = CacheMetrics()


# ─── Middleware: Security Headers + IP Logging ───────────────────

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Security headers + логирование IP каждого запроса."""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"→ {client_ip} {request.method} {request.url.path}")

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# ─── Authentication & Rate Limiting Dependencies ─────────────────

async def get_client_info(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
) -> tuple[str, bool]:
    """
    Извлекает client_id и флаг аутентификации.

    Возвращает (client_id, is_authenticated):
    - С токеном: (token_prefix, True)
    - Без токена: (ip_address, False)
    """
    client_ip = request.client.host if request.client else "unknown"

    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            if secrets.compare_digest(token, _SERVICE_TOKEN):
                return (f"auth:{token[:8]}...", True)
            else:
                logger.warning(f"Invalid token from {client_ip}")
                raise HTTPException(
                    status_code=403,
                    detail="Invalid authentication token",
                )

    return (client_ip, False)


async def rate_limit_check(
    client_info: tuple[str, bool] = Depends(get_client_info),
) -> tuple[str, bool]:
    """Rate limiting с разными лимитами для auth/anon."""
    client_id, is_authenticated = client_info
    limiter = _get_rate_limiter(client_id, is_authenticated)

    if not limiter.consume():
        limit = RATE_LIMIT_AUTHENTICATED if is_authenticated else RATE_LIMIT_ANONYMOUS
        logger.warning(
            f"Rate limit exceeded: {client_id} "
            f"(auth={is_authenticated}, limit={limit}/{RATE_LIMIT_WINDOW}s)"
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded. "
                f"Limit: {limit} requests per {RATE_LIMIT_WINDOW}s. "
                f"{'Use Bearer token for higher limits.' if not is_authenticated else 'Try again later.'}"
            ),
            headers={
                "Retry-After": str(RATE_LIMIT_WINDOW),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    return client_info


# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════

class ScreenshotRequest(BaseModel):
    url: str = Field(..., description="URL для скриншота")
    full_page: bool = Field(False, description="Полная страница")
    width: int = Field(1920, ge=MIN_VIEWPORT_WIDTH, le=MAX_VIEWPORT_WIDTH)
    height: int = Field(1080, ge=MIN_VIEWPORT_HEIGHT, le=MAX_VIEWPORT_HEIGHT)
    wait_for: str | None = Field(None, description="CSS-селектор для ожидания")
    wait_ms: int = Field(0, ge=0, le=MAX_WAIT_MS, description="Дополнительное ожидание (мс)")
    stealth: bool = Field(True, description="Применить антидетект")
    format: str = Field("png", description="Формат: png или pdf")

    @field_validator("url")
    @classmethod
    def url_must_be_valid(cls, v):
        try:
            return validate_url(v)
        except URLValidationError as e:
            raise ValueError(str(e))

    @field_validator("wait_for")
    @classmethod
    def css_selector_safe(cls, v):
        if v is None:
            return v
        if any(c in v for c in ["<", ">", "{", "}", "\\", "\x00"]):
            raise ValueError("CSS селектор содержит недопустимые символы")
        if len(v) > 256:
            raise ValueError("CSS селектор слишком длинный (макс. 256)")
        return v


class ScreenshotResponse(BaseModel):
    success: bool
    url: str
    screenshot_url: str | None = None
    cached: bool = False
    load_time_ms: float = 0
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════
# CACHE HELPERS
# ═══════════════════════════════════════════════════════════════════

def _ensure_secure_cache_dir():
    """Создать кэш-директорию с безопасными правами (0700)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CACHE_DIR, 0o700)


def cache_key(url: str, full_page: bool, width: int, height: int, fmt: str = "png") -> str:
    """SHA-256 ключ кэша."""
    data = f"{url}:{full_page}:{width}:{height}:{fmt}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_cached_screenshot(key: str) -> Path | None:
    """Получить скриншот из кэша с защитой от path traversal."""
    if not re.match(r"^[a-f0-9]{64}$", key):
        logger.warning(f"Invalid cache key format: {key[:20]}...")
        return None

    for ext in ("png", "pdf"):
        path = CACHE_DIR / f"{key}.{ext}"
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(CACHE_DIR.resolve() + "/")):
                logger.warning(f"Path traversal attempt on cache key: {key[:20]}")
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


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/health")
async def health(
    request: Request,
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """Health check (rate limited per IP)."""
    return {
        "status": "ok",
        "service": "screenshot-as-a-Service",
        "version": "1.0.0-secure",
        "cache_hit_rate": f"{cache_metrics.rate:.1%}",
        "total_requests": cache_metrics.total,
    }


@app.get("/metrics")
async def metrics(
    request: Request,
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """Prometheus-compatible metrics (rate limited per IP)."""
    data, content_type = get_metrics_output()
    return Response(content=data, media_type=content_type)


@app.post("/screenshot", response_model=ScreenshotResponse)
async def create_screenshot(
    request: ScreenshotRequest,
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """
    Создать скриншот страницы.

    Аутентификация через Authorization: Bearer <token> (опционально).
    Без токена: 100 req/min. С токеном: 1000 req/min.
    """
    client_id, is_authenticated = client_info
    start = time.time()

    # Проверить кэш
    key = cache_key(request.url, request.full_page, request.width, request.height, request.format)
    cached = get_cached_screenshot(key)
    if cached:
        logger.info(f"[{client_id}] Cache hit: {request.url}")
        cache_metrics.hit()
        SS_REQUESTS.labels(status="cached", format=request.format).inc()
        return ScreenshotResponse(
            success=True,
            url=request.url,
            screenshot_url=f"/screenshot/download/{key}",
            cached=True,
            load_time_ms=(time.time() - start) * 1000,
        )

    cache_metrics.miss()
    _browser_active = False

    try:
        with LatencyTimer(SS_LATENCY):
            async with BrowserManager(
                headless=True,
                timeout=NAVIGATION_TIMEOUT_MS,
                viewport={"width": request.width, "height": request.height},
            ) as browser:
                _browser_active = True
                SS_ACTIVE_BROWSERS.inc()
                page = await browser.new_page()

                if request.stealth:
                    await apply_stealth(page, StealthConfig.minimal())

                # DNS resolve перед навигацией (защита от DNS rebinding с TTL)
                from urllib.parse import urlparse
                import socket
                from ipaddress import ip_address as parse_ip_address
                _goto_url = request.url
                _goto_parsed = urlparse(_goto_url)
                _goto_port = _goto_parsed.port or (443 if _goto_parsed.scheme == "https" else 80)
                try:
                    _resolved = socket.getaddrinfo(_goto_parsed.hostname, _goto_port)
                    for _fam, _type, _proto, _cname, _sockaddr in _resolved:
                        _addr = parse_ip_address(_sockaddr[0])
                        if _addr.is_private or _addr.is_loopback or _addr.is_link_local:
                            raise HTTPException(
                                status_code=400,
                                detail=f"DNS rebinding detected: {_goto_parsed.hostname} resolves to internal IP {_addr}"
                            )
                except socket.gaierror:
                    raise HTTPException(status_code=400, detail=f"DNS resolution failed for: {_goto_parsed.hostname}")

                await page.goto(_goto_url, wait_until="domcontentloaded")

                if request.wait_for:
                    try:
                        await page.wait_for_selector(
                            request.wait_for, timeout=10000
                        )
                    except Exception:
                        logger.warning(
                            f"[{client_id}] Timeout waiting for selector: {request.wait_for}"
                        )

                if request.wait_ms > 0:
                    await page.wait_for_timeout(request.wait_ms)

                maker = ScreenshotMaker(str(CACHE_DIR))

                if request.format == "pdf":
                    path = await maker.pdf(page, prefix=key)
                elif request.full_page:
                    path = await maker.full_page(page, prefix=key)
                else:
                    path = await maker.viewport(page, prefix=key)

                os.chmod(path, 0o600)

                load_time = (time.time() - start) * 1000
                logger.info(
                    f"[{client_id}] Screenshot OK: {request.url} → {path} "
                    f"({load_time:.0f}ms, auth={is_authenticated})"
                )

                SS_REQUESTS.labels(status="ok", format=request.format).inc()

                return ScreenshotResponse(
                    success=True,
                    url=request.url,
                    screenshot_url=f"/screenshot/download/{key}",
                    cached=False,
                    load_time_ms=load_time,
                )

    except Exception as e:
        error_type = "unknown"
        error_str = str(e).lower()
        if "launch" in error_str:
            error_type = "launch"
        elif "navig" in error_str:
            error_type = "navigation"
        elif "timeout" in error_str:
            error_type = "timeout"
        elif "screenshot" in error_str:
            error_type = "screenshot"

        SS_BROWSER_ERRORS.labels(error_type=error_type).inc()
        SS_REQUESTS.labels(status="error", format=request.format).inc()
        logger.error(f"[{client_id}] Screenshot failed for {request.url}: {e}")

        raise HTTPException(
            status_code=500,
            detail="Screenshot generation failed. Check URL and try again.",
        )

    finally:
        if _browser_active:
            SS_ACTIVE_BROWSERS.dec()


@app.get("/screenshot/download/{key}")
async def download_screenshot(
    key: str,
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """
    Скачать скриншот по ключу.

    Аутентификация через Authorization: Bearer <token> (опционально).
    """
    client_id, _ = client_info

    if not re.match(r"^[a-f0-9]{64}$", key):
        raise HTTPException(status_code=400, detail="Invalid key format")

    for ext in ("png", "pdf"):
        path = CACHE_DIR / f"{key}.{ext}"
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(CACHE_DIR.resolve() + "/")):
                logger.warning(f"[{client_id}] Path traversal attempt: {key[:20]}")
                raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="Screenshot not found")

        if resolved.exists():
            media_type = "image/png" if ext == "png" else "application/pdf"
            logger.info(f"[{client_id}] Download: {key}.{ext}")
            return FileResponse(resolved, media_type=media_type)

    raise HTTPException(status_code=404, detail="Screenshot not found")


@app.get("/screenshot")
async def get_screenshot_get(
    url: str = Query(..., description="URL для скриншота"),
    full_page: bool = Query(False),
    width: int = Query(1920),
    height: int = Query(1080),
    format: str = Query("png"),
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """
    GET-вариант для простых запросов.

    Аутентификация через Authorization: Bearer <token> (опционально).
    """
    request = ScreenshotRequest(
        url=url,
        full_page=full_page,
        width=width,
        height=height,
        format=format,
    )
    return await create_screenshot(request, client_info)


@app.delete("/cache")
async def clear_cache(
    client_info: tuple[str, bool] = Depends(rate_limit_check),
):
    """
    Очистить кэш скриншотов.

    Аутентификация через Authorization: Bearer <token> (опционально).
    """
    client_id, _ = client_info
    count = 0
    for f in CACHE_DIR.iterdir():
        try:
            resolved = f.resolve()
            if str(resolved).startswith(str(CACHE_DIR.resolve() + "/")):
                resolved.unlink()
                count += 1
        except Exception:
            pass
    logger.info(f"[{client_id}] Cache cleared: {count} files")
    return {"cleared": count}


# ═══════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8190)
