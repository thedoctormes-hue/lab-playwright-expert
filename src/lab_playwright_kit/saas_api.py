"""
SaaS Parsing API — FastAPI приложение для парсинга данных из браузера.

Эндпоинты:
  POST /api/v1/parse          — парсинг URL по схеме ниши
  POST /api/v1/parse/batch    — батч-парсинг нескольких URL
  GET  /api/v1/niches         — список доступных ниш
  GET  /api/v1/niches/{name}  — детали ниши (поля, селекторы)
  POST /api/v1/auth/login     — авторизация на платформе
  POST /api/v1/auth/check     — проверка авторизации
  GET  /api/v1/auth/sessions  — список активных сессий
  DELETE /api/v1/auth/sessions/{name} — удаление сессии
  GET  /api/v1/health         — health check
  GET  /api/v1/status         — статус системы (воркеры, очередь, uptime)

Использование:
    >>> import uvicorn
    >>> from lab_playwright_kit.saas_api import create_app
    >>> app = create_app()
    >>> uvicorn.run(app, host="0.0.0.0", port=8190)

Curl примеры:
    # Парсинг статьи с Хабра
    curl -X POST http://localhost:8190/api/v1/parse \\
         -H "Content-Type: application/json" \\
         -d '{"url": "https://habr.com/ru/articles/123456/", "niche": "habr"}'

    # Батч-парсинг
    curl -X POST http://localhost:8190/api/v1/parse/batch \\
         -H "Content-Type: application/json" \\
         -d '{"urls": ["https://habr.com/ru/articles/123/", "https://vc.ru/marketing/456"], "niche": "habr"}'

    # Авторизация
    curl -X POST http://localhost:8190/api/v1/auth/login \\
         -H "Content-Type: application/json" \\
         -d '{"platform": "habr", "username": "user@mail.ru", "password": "pass"}'
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

from .browser import BrowserManager
from .browser_auth import (
    AUTH_PRESETS,
    AuthResultStatus,
    BrowserAuthManager,
)
from .data_parser import (
    SCHEMA_REGISTRY,
    NicheType,
    ParseResult,
    detect_niche,
    export_to_json,
    get_schema,
)
from .vpn_proxy import VPNProxyManager
from .account_finder import AccountFinder, FoundAccount, SearchReport, UsernamePermuter
from .platform_registry import PlatformRegistry, CheckType


# ─── Pydantic Models ────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    """Запрос на парсинг одного URL."""
    url: str = Field(..., description="URL для парсинга")
    niche: str = Field("", description="Ниша (пусто = автоопределение)")
    timeout: float = Field(30.0, description="Таймаут в секундах")
    proxy_url: str = Field("", description="Прокси (пусто = direct)")
    wait_for: str = Field("", description="Селектор для ожидания перед парсингом")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Доп. данные")


class BatchParseRequest(BaseModel):
    """Запрос на батч-парсинг."""
    urls: list[str] = Field(..., min_length=1, max_length=50, description="Список URL")
    niche: str = Field("", description="Ниша (пусто = автоопределение)")
    timeout: float = Field(30.0, description="Таймаут на каждый URL")
    proxy_url: str = Field("", description="Прокси")
    max_concurrency: int = Field(3, ge=1, le=10, description="Параллельные воркеры")
    delay_between: float = Field(1.0, ge=0, description="Задержка между запросами (сек)")


class AuthLoginRequest(BaseModel):
    """Запрос на авторизацию."""
    platform: str = Field(..., description="Платформа (habr, vcru, twitter, telegram)")
    username: str = Field(..., description="Логин / email")
    password: str = Field(..., description="Пароль")
    proxy_url: str = Field("", description="Прокси")
    force: bool = Field(False, description="Принудительная переавторизация")


class AuthCheckRequest(BaseModel):
    """Запрос на проверку авторизации."""
    platform: str = Field(..., description="Платформа")
    username: str = Field("", description="Логин (пусто = любая сессия)")


class Auth2FARequest(BaseModel):
    """Запрос на ввод 2FA кода."""
    platform: str = Field(..., description="Платформа")
    username: str = Field(..., description="Логин")
    code: str = Field(..., description="2FA код")


class PublishRequest(BaseModel):
    """Запрос на публикацию контента на платформе."""
    platform: str = Field(..., description="Платформа (habr, vcru, tenchat)")
    title: str = Field("", description="Заголовок поста/статьи")
    content: str = Field(..., description="Текст контента (HTML или plain text)")
    username: str = Field("", description="Логин (пусто = первая доступная сессия)")
    proxy_url: str = Field("", description="Прокси")
    timeout: float = Field(60.0, description="Таймаут в секундах")
    dry_run: bool = Field(False, description="Тестовый прогон без публикации")


class ParseResponse(BaseModel):
    """Ответ парсинга."""
    success: bool
    url: str
    niche: str
    data: dict[str, Any]
    confidence: float
    parse_time_ms: float
    page_title: str
    domain: str
    errors: list[str]
    parsed_at: str
    request_id: str


class BatchParseResponse(BaseModel):
    """Ответ батч-парсинга."""
    total: int
    successful: int
    failed: int
    results: list[ParseResponse]
    elapsed_seconds: float
    request_id: str


class PublishResponse(BaseModel):
    """Ответ публикации."""
    success: bool
    platform: str
    url: str
    message: str
    elapsed_seconds: float
    error: str
    dry_run: bool


class AuthResponse(BaseModel):
    """Ответ авторизации."""
    success: bool
    status: str
    platform: str
    username: str
    message: str
    session_name: str
    cookies_count: int
    elapsed_seconds: float
    error: str


class NicheInfo(BaseModel):
    """Информация о нише."""
    name: str
    display_name: str
    description: str
    fields: list[str]
    url_patterns: list[str]
    required_fields: list[str]


class OSINTSearchRequest(BaseModel):
    """Запрос на OSINT-поиск по username."""
    username: str = Field(..., description="Имя пользователя для поиска", min_length=1, max_length=100)
    platforms: list[str] = Field(default_factory=list, description="Список платформ (пусто = все)")
    tags: list[str] = Field(default_factory=list, description="Фильтр по тегам (social, ru, coding)")
    top_n: int = Field(50, ge=1, le=51, description="Максимум платформ для проверки")
    permute: bool = Field(False, description="Искать вариации ника")
    timeout: float = Field(15.0, ge=5.0, le=60.0, description="Таймаут на платформу (сек)")


class OSINTAccountResponse(BaseModel):
    """Найденный аккаунт."""
    platform: str
    username: str
    url: str
    status: str
    confidence: float
    source: str
    tags: list[str]


class OSINTSearchResponse(BaseModel):
    """Ответ OSINT-поиска."""
    query: str
    total_found: int
    checked: int
    elapsed_seconds: float
    accounts: list[OSINTAccountResponse]


class OSINTPlatformInfo(BaseModel):
    """Информация о платформе."""
    name: str
    url_template: str
    check_type: str
    tags: list[str]
    disabled: bool


class OSINTPlatformsResponse(BaseModel):
    """Список платформ."""
    total: int
    platforms: list[OSINTPlatformInfo]


class HealthResponse(BaseModel):
    """Health check ответ."""
    status: str
    version: str
    uptime_seconds: float
    timestamp: str


class StatusResponse(BaseModel):
    """Статус системы."""
    status: str
    version: str
    uptime_seconds: float
    browser_active: bool
    active_sessions: int
    available_niches: int
    available_presets: int
    proxy_count: int
    timestamp: str


# ─── App State ───────────────────────────────────────────────────────────────

@dataclass
class AppState:
    """Состояние приложения."""
    browser_manager: BrowserManager | None = None
    auth_manager: BrowserAuthManager | None = None
    proxy_manager: VPNProxyManager | None = None
    browser_engine: str = "playwright"
    browser_humanize: bool = False
    start_time: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0


# ─── App Factory ─────────────────────────────────────────────────────────────

def create_app(
    browser_manager: BrowserManager | None = None,
    auth_manager: BrowserAuthManager | None = None,
    proxy_manager: VPNProxyManager | None = None,
    browser_engine: str = "playwright",
    browser_humanize: bool = False,
) -> FastAPI:
    """Создать FastAPI приложение.

    Args:
        browser_manager: BrowserManager (None = создаст при старте)
        auth_manager: BrowserAuthManager (None = создаст при старте)
        proxy_manager: VPNProxyManager (None = без прокси)
        browser_engine: Движок браузера — "playwright" или "cloakbrowser"
        browser_humanize: Включить humanize (только для cloakbrowser)

    Returns:
        FastAPI app
    """
    state = AppState(
        browser_manager=browser_manager,
        auth_manager=auth_manager,
        proxy_manager=proxy_manager,
        browser_engine=browser_engine,
        browser_humanize=browser_humanize,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Жизненный цикл приложения."""
        # Startup
        logger.info("SaaS API starting up...")

        if not state.browser_manager:
            state.browser_manager = BrowserManager(
                headless=True,
                engine=browser_engine,
                humanize=browser_humanize,
                stealth="standard" if browser_engine == "playwright" else None,
            )
        await state.browser_manager.start()

        if not state.auth_manager:
            state.auth_manager = BrowserAuthManager(
                browser_manager=state.browser_manager,
                proxy_manager=state.proxy_manager,
            )

        logger.info("SaaS API ready")
        yield

        # Shutdown
        logger.info("SaaS API shutting down...")
        if state.browser_manager:
            await state.browser_manager.stop()
        logger.info("SaaS API stopped")

    app = FastAPI(
        title="Lab Playwright Kit — SaaS Parsing API",
        description="API для парсинга данных из браузера с антидетектом и авторизацией",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Health & Status ─────────────────────────────────────────────────

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        """Health check."""
        return HealthResponse(
            status="healthy",
            version="2.0.0",
            uptime_seconds=time.time() - state.start_time,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @app.get("/api/v1/status", response_model=StatusResponse, tags=["System"])
    async def system_status():
        """Статус системы."""
        sessions = []
        if state.auth_manager:
            sessions = state.auth_manager.list_sessions()

        proxies = 0
        if state.proxy_manager:
            proxies = len(state.proxy_manager.list_proxies())

        return StatusResponse(
            status="running",
            version="2.0.0",
            uptime_seconds=time.time() - state.start_time,
            browser_active=state.browser_manager is not None,
            active_sessions=len(sessions),
            available_niches=len(SCHEMA_REGISTRY),
            available_presets=len(AUTH_PRESETS),
            proxy_count=proxies,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ─── Parse ───────────────────────────────────────────────────────────

    @app.post("/api/v1/parse", response_model=ParseResponse, tags=["Parsing"])
    async def parse_url(request: ParseRequest):
        """Парсинг одного URL по схеме ниши.

        Автоматически определяет нишу по URL если не указана.
        Поддерживает все 10 ниш: ecommerce, news, realty, medtech, jobs, auto, habr, vcru, twitter, telegram.
        """
        request_id = str(uuid.uuid4())[:8]
        state.request_count += 1

        try:
            # Определить нишу
            niche_type = None
            if request.niche:
                try:
                    niche_type = NicheType(request.niche.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown niche: {request.niche}. Available: {[n.value for n in SCHEMA_REGISTRY]}"
                    )
            else:
                niche_type = detect_niche(request.url)
                if niche_type == NicheType.GENERIC:
                    # Пробуем по домену
                    for nt, schema in SCHEMA_REGISTRY.items():
                        for pattern in schema.url_patterns:
                            if pattern.replace("\\", "") in request.url:
                                niche_type = nt
                                break
                        if niche_type != NicheType.GENERIC:
                            break

            # Получить схему
            try:
                schema = get_schema(niche_type)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"No schema for niche: {niche_type}"
                )

            # Парсинг
            start = time.time()
            page = await state.browser_manager.new_page()

            try:
                await page.goto(request.url, wait_until="domcontentloaded", timeout=int(request.timeout * 1000))

                if request.wait_for:
                    await page.wait_for_selector(request.wait_for, timeout=5000)

                # Извлечь данные по схеме
                data: dict[str, Any] = {}
                errors: list[str] = []

                for field_mapping in schema.fields:
                    value = None
                    for selector in field_mapping.selectors:
                        try:
                            el = page.locator(selector).first
                            if await el.is_visible(timeout=2000):
                                if field_mapping.attribute:
                                    value = await el.get_attribute(field_mapping.attribute)
                                else:
                                    if field_mapping.is_list:
                                        items = page.locator(selector)
                                        count = await items.count()
                                        value = []
                                        for i in range(count):
                                            item = items.nth(i)
                                            if field_mapping.attribute:
                                                v = await item.get_attribute(field_mapping.attribute)
                                            else:
                                                v = await item.inner_text()
                                            if v:
                                                value.append(v.strip())
                                    else:
                                        value = await el.inner_text()
                                break
                        except Exception:
                            continue

                    # Применить regex
                    if value and field_mapping.regex and not field_mapping.is_list:
                        import re
                        match = re.search(field_mapping.regex, str(value))
                        if match:
                            value = match.group(0)

                    # Применить transform
                    if value and field_mapping.transform and not field_mapping.is_list:
                        from .data_parser import TRANSFORMS
                        transform_fn = TRANSFORMS.get(field_mapping.transform)
                        if transform_fn:
                            try:
                                value = transform_fn(value)
                            except Exception:
                                pass

                    if value is None:
                        value = field_mapping.default

                    data[field_mapping.name] = value

                    if field_mapping.required and value is None:
                        errors.append(f"Required field not found: {field_mapping.name}")

                # Заголовок страницы
                page_title = await page.title()
                domain = page.url.split("/")[2] if "/" in page.url else ""

                # Confidence
                required = schema.get_required_fields()
                if required:
                    filled = sum(1 for f in required if data.get(f.name) is not None)
                    confidence = filled / len(required)
                else:
                    total = len(schema.fields)
                    filled = sum(1 for f in schema.fields if data.get(f.name) is not None)
                    confidence = filled / total if total > 0 else 0.0

                elapsed_ms = (time.time() - start) * 1000

                return ParseResponse(
                    success=confidence > 0.3 and not any(
                        e.startswith("Required") for e in errors
                    ),
                    url=request.url,
                    niche=niche_type.value,
                    data=data,
                    confidence=round(confidence, 2),
                    parse_time_ms=round(elapsed_ms, 1),
                    page_title=page_title,
                    domain=domain,
                    errors=errors,
                    parsed_at=datetime.now(timezone.utc).isoformat(),
                    request_id=request_id,
                )

            finally:
                await page.close()

        except HTTPException:
            raise
        except Exception as e:
            state.error_count += 1
            logger.error(f"Parse error [{request_id}]: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/parse/batch", response_model=BatchParseResponse, tags=["Parsing"])
    async def parse_batch(request: BatchParseRequest):
        """Батч-парсинг нескольких URL.

        Параллельное выполнение с ограничением concurrency.
        Задержка между запросами для избежания rate limiting.
        """
        request_id = str(uuid.uuid4())[:8]
        start = time.time()
        results: list[ParseResponse] = []

        semaphore = asyncio.Semaphore(request.max_concurrency)

        async def _parse_one(url: str) -> ParseResponse:
            async with semaphore:
                try:
                    resp = await parse_url(ParseRequest(
                        url=url,
                        niche=request.niche,
                        timeout=request.timeout,
                        proxy_url=request.proxy_url,
                    ))
                    if request.delay_between > 0:
                        await asyncio.sleep(request.delay_between)
                    return resp
                except HTTPException as e:
                    return ParseResponse(
                        success=False,
                        url=url,
                        niche=request.niche or detect_niche(url).value,
                        data={},
                        confidence=0,
                        parse_time_ms=0,
                        page_title="",
                        domain="",
                        errors=[e.detail],
                        parsed_at=datetime.now(timezone.utc).isoformat(),
                        request_id=request_id,
                    )

        tasks = [_parse_one(url) for url in request.urls]
        results = await asyncio.gather(*tasks)

        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return BatchParseResponse(
            total=len(results),
            successful=successful,
            failed=failed,
            results=results,
            elapsed_seconds=round(time.time() - start, 2),
            request_id=request_id,
        )

    # ─── Niches ──────────────────────────────────────────────────────────

    @app.get("/api/v1/niches", response_model=list[NicheInfo], tags=["Niches"])
    async def list_niches():
        """Список всех доступных ниш для парсинга."""
        niches = []
        for niche_type, schema in SCHEMA_REGISTRY.items():
            niches.append(NicheInfo(
                name=niche_type.value,
                display_name=schema.name,
                description=schema.description,
                fields=schema.get_field_names(),
                url_patterns=schema.url_patterns,
                required_fields=[f.name for f in schema.get_required_fields()],
            ))
        return niches

    @app.get("/api/v1/niches/{name}", response_model=NicheInfo, tags=["Niches"])
    async def get_niche(name: str):
        """Детали ниши по имени."""
        try:
            niche_type = NicheType(name.lower())
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown niche: {name}. Available: {[n.value for n in SCHEMA_REGISTRY]}"
            )

        schema = get_schema(niche_type)
        return NicheInfo(
            name=niche_type.value,
            display_name=schema.name,
            description=schema.description,
            fields=schema.get_field_names(),
            url_patterns=schema.url_patterns,
            required_fields=[f.name for f in schema.get_required_fields()],
        )

    # ─── Auth ────────────────────────────────────────────────────────────

    @app.post("/api/v1/auth/login", response_model=AuthResponse, tags=["Auth"])
    async def auth_login(request: AuthLoginRequest):
        """Авторизация на платформе.

        Поддерживаемые платформы: habr, vcru, twitter, telegram.
        Сессия сохраняется и может быть переиспользована.
        """
        result = await state.auth_manager.login(
            platform=request.platform,
            username=request.username,
            password=request.password,
            proxy_url=request.proxy_url,
            force=request.force,
        )

        return AuthResponse(
            success=result.success,
            status=result.status.value,
            platform=result.platform,
            username=result.username,
            message=result.message,
            session_name=result.session_name,
            cookies_count=result.cookies_count,
            elapsed_seconds=round(result.elapsed_seconds, 2),
            error=result.error,
        )

    @app.post("/api/v1/auth/check", response_model=AuthResponse, tags=["Auth"])
    async def auth_check(request: AuthCheckRequest):
        """Проверка авторизации на платформе."""
        is_auth = await state.auth_manager.check_auth(
            platform=request.platform,
            username=request.username,
        )

        return AuthResponse(
            success=is_auth,
            status="authenticated" if is_auth else "not_authenticated",
            platform=request.platform,
            username=request.username,
            message="Authenticated" if is_auth else "Not authenticated",
            session_name="",
            cookies_count=0,
            elapsed_seconds=0,
            error="",
        )

    @app.post("/api/v1/auth/2fa", response_model=AuthResponse, tags=["Auth"])
    async def auth_2fa(request: Auth2FARequest):
        """Ввод 2FA кода после логина."""
        result = await state.auth_manager.handle_2fa(
            platform=request.platform,
            username=request.username,
            code=request.code,
        )

        return AuthResponse(
            success=result.success,
            status=result.status.value,
            platform=result.platform,
            username=result.username,
            message=result.message,
            session_name=result.session_name,
            cookies_count=result.cookies_count,
            elapsed_seconds=round(result.elapsed_seconds, 2),
            error=result.error,
        )

    @app.get("/api/v1/auth/sessions", tags=["Auth"])
    async def auth_list_sessions(platform: str = Query("", description="Фильтр по платформе")):
        """Список активных сессий."""
        sessions = state.auth_manager.list_sessions(platform=platform)
        return {
            "total": len(sessions),
            "sessions": sessions,
        }

    @app.delete("/api/v1/auth/sessions/{platform}/{username}", tags=["Auth"])
    async def auth_delete_session(platform: str, username: str):
        """Удалить сохранённую сессию."""
        state.auth_manager.delete_session(platform, username)
        return {"message": f"Session deleted: {platform}_{username}"}

    @app.get("/api/v1/auth/presets", tags=["Auth"])
    async def auth_list_presets():
        """Список доступных пресетов авторизации."""
        presets = []
        for name, preset in AUTH_PRESETS.items():
            presets.append({
                "name": name,
                "platform": preset.platform,
                "login_url": preset.login_url,
                "auth_check_url": preset.auth_check_url,
                "has_captcha_detection": bool(preset.captcha_selector),
                "has_2fa_detection": bool(preset.two_fa_selector),
                "notes": preset.notes,
            })
        return {"total": len(presets), "presets": presets}

    # ─── OSINT ───────────────────────────────────────────────────────────

    @app.post("/api/v1/osint/search", response_model=OSINTSearchResponse, tags=["OSINT"])
    async def osint_search(request: OSINTSearchRequest):
        """OSINT-поиск: найти аккаунты по username на множестве платформ.

        Проверяет наличие аккаунта на 50+ платформах одновременно.
        Работает без браузера — через HTTP-запросы (быстро).

        Пример:
            curl -X POST http://localhost:8190/api/v1/osint/search \\
                 -H "Content-Type: application/json" \\
                 -d '{"username": "torvalds", "tags": ["coding"]}'
        """
        request_id = str(uuid.uuid4())[:8]
        state.request_count += 1

        try:
            registry = PlatformRegistry()
            registry.load_defaults()
            finder = AccountFinder(
                registry=registry,
                max_concurrent=10,
                timeout=request.timeout,
            )

            # Определить платформы
            if request.platforms:
                profiles = []
                for name in request.platforms:
                    p = registry.get(name)
                    if p and not p.disabled:
                        profiles.append(p)
                # Если указаны конкретные платформы, ищем по ним
                report = await finder.search(
                    username=request.username,
                    platforms=request.platforms,
                    top_n=request.top_n,
                    permute=request.permute,
                )
            elif request.tags:
                report = await finder.search(
                    username=request.username,
                    tags=request.tags,
                    top_n=request.top_n,
                    permute=request.permute,
                )
            else:
                report = await finder.search(
                    username=request.username,
                    top_n=request.top_n,
                    permute=request.permute,
                )

            accounts = [
                OSINTAccountResponse(
                    platform=a.platform,
                    username=a.username,
                    url=a.url,
                    status=a.status,
                    confidence=a.confidence,
                    source=a.source,
                    tags=a.tags,
                )
                for a in report.found
            ]

            return OSINTSearchResponse(
                query=report.query,
                total_found=report.total_found,
                checked=report.checked,
                elapsed_seconds=round(report.elapsed_seconds, 2),
                accounts=accounts,
            )

        except Exception as e:
            state.error_count += 1
            logger.error(f"OSINT search error [{request_id}]: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/osint/platforms", response_model=OSINTPlatformsResponse, tags=["OSINT"])
    async def osint_list_platforms(
        tag: str = Query("", description="Фильтр по тегу"),
        disabled: bool = Query(False, description="Включить отключённые"),
    ):
        """Список всех доступных платформ для OSINT-поиска."""
        registry = PlatformRegistry()
        registry.load_defaults()

        if tag:
            profiles = registry.filter_by_tag(tag)
        else:
            profiles = registry.all()

        if not disabled:
            profiles = [p for p in profiles if not p.disabled]

        return OSINTPlatformsResponse(
            total=len(profiles),
            platforms=[
                OSINTPlatformInfo(
                    name=p.name,
                    url_template=p.url_template,
                    check_type=p.check_type.value,
                    tags=p.tags,
                    disabled=p.disabled,
                )
                for p in profiles
            ],
        )

    @app.get("/api/v1/osint/search/{username}", response_model=OSINTSearchResponse, tags=["OSINT"])
    async def osint_search_get(
        username: str,
        platforms: str = Query("", description="Список платформ через запятую"),
        tags: str = Query("", description="Теги через запятую"),
        top_n: int = Query(50, ge=1, le=51),
        permute: bool = Query(False),
    ):
        """OSINT-поиск через GET (для быстрой проверки из браузера).

        Пример:
            curl http://localhost:8190/api/v1/osint/search/torvalds?tags=coding
        """
        platform_list = [p.strip() for p in platforms.split(",") if p.strip()] if platforms else []
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        req = OSINTSearchRequest(
            username=username,
            platforms=platform_list,
            tags=tag_list,
            top_n=top_n,
            permute=permute,
        )
        return await osint_search(req)

    # ─── Publish ─────────────────────────────────────────────────────────

    @app.post("/api/v1/publish", response_model=PublishResponse, tags=["Publish"])
    async def publish_content(request: PublishRequest):
        """Опубликовать контент на платформе.

        Требует предварительной авторизации через POST /api/v1/auth/login.
        Поддерживает: habr, vcru, tenchat.
        """
        start = time.time()

        try:
            # Проверяем авторизацию
            is_auth = await state.auth_manager.check_auth(
                platform=request.platform,
                username=request.username,
            )
            if not is_auth:
                return PublishResponse(
                    success=False,
                    platform=request.platform,
                    url="",
                    message="Not authenticated",
                    elapsed_seconds=time.time() - start,
                    error="NOT_AUTHENTICATED",
                    dry_run=request.dry_run,
                )

            if request.dry_run:
                return PublishResponse(
                    success=True,
                    platform=request.platform,
                    url="",
                    message="Dry run — auth OK, skip publish",
                    elapsed_seconds=time.time() - start,
                    error="",
                    dry_run=True,
                )

            # Публикация через браузер
            page = await state.browser_manager.new_page()

            try:
                url = await _publish_to_platform(
                    page, request.platform, request.title, request.content,
                    timeout=request.timeout,
                )
                elapsed = time.time() - start

                return PublishResponse(
                    success=True,
                    platform=request.platform,
                    url=url,
                    message=f"Published to {request.platform}",
                    elapsed_seconds=round(elapsed, 2),
                    error="",
                    dry_run=False,
                )
            finally:
                await page.close()

        except Exception as e:
            state.error_count += 1
            logger.error(f"Publish error [{request.platform}]: {e}")
            return PublishResponse(
                success=False,
                platform=request.platform,
                url="",
                message=str(e),
                elapsed_seconds=time.time() - start,
                error=str(e),
                dry_run=request.dry_run,
            )

    return app


# ─── Publish Helpers ─────────────────────────────────────────────────────────

async def _publish_to_platform(
    page, platform: str, title: str, content: str, timeout: float = 60.0,
) -> str:
    """Опубликовать контент на платформе через браузер.

    Args:
        page: Playwright page (уже авторизованный)
        platform: Платформа (habr, vcru, tenchat)
        title: Заголовок
        content: Текст
        timeout: Таймаут

    Returns:
        URL опубликованного поста
    """
    from .browser_auth import AUTH_PRESETS

    preset = AUTH_PRESETS.get(platform)
    if not preset:
        raise ValueError(f"Unknown platform: {platform}")

    # Навигация на страницу публикации
    publish_urls = {
        "habr": "https://habr.com/ru/articles/draft/",
        "vcru": "https://vc.ru/write",
        "tenchat": "https://tenchat.ru/post/new",
    }
    url = publish_urls.get(platform, preset.auth_check_url)
    await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
    await page.wait_for_timeout(3000)

    # Заполнить заголовок
    title_selectors = {
        "habr": "input[placeholder*='заголовок'], #title, .form__title",
        "vcru": "input[name='title'], input[placeholder*='заголовок']",
        "tenchat": "input[name='title'], input[placeholder*='заголовок']",
    }
    for sel in title_selectors.get(platform, "").split(", "):
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                await el.fill(title)
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    # Заполнить контент
    editor_selectors = {
        "habr": ".ProseMirror, .ce-block, #text",
        "vcru": ".ProseMirror, .ql-editor, textarea[name='content']",
        "tenchat": ".ProseMirror, textarea[name='content'], [contenteditable='true']",
    }
    for sel in editor_selectors.get(platform, "").split(", "):
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                await page.wait_for_timeout(500)
                # Вводить по частям для имитации человека
                chunk_size = 500
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i + chunk_size]
                    await page.keyboard.type(chunk, delay=10)
                    await page.wait_for_timeout(200)
                break
        except Exception:
            continue

    await page.wait_for_timeout(2000)

    # Сохранить/опубликовать
    save_selectors = {
        "habr": "button:has-text('Сохранить'), button:has-text('Черновик')",
        "vcru": "button:has-text('Сохранить'), button:has-text('Черновик')",
        "tenchat": "button:has-text('Опубликовать'), button:has-text('Отправить')",
    }
    for sel in save_selectors.get(platform, "").split(", "):
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    return page.url


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def main():
    """Запуск SaaS API сервера."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Lab Playwright Kit — SaaS Parsing API")
    parser.add_argument("--host", default="0.0.0.0", description="Host")
    parser.add_argument("--port", type=int, default=8190, description="Port")
    parser.add_argument("--headless", action="store_true", default=True, description="Headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", description="Show browser")
    parser.add_argument("--proxy-config", default="", description="Path to proxy YAML config")
    parser.add_argument("--db-path", default="accounts.db", description="Accounts DB path")
    parser.add_argument("--session-dir", default=".sessions", description="Sessions directory")
    parser.add_argument(
        "--engine", choices=["playwright", "cloakbrowser"], default="playwright",
        description="Browser engine: playwright (default) or cloakbrowser (stealth C++ patches)"
    )
    parser.add_argument("--humanize", action="store_true", default=False, description="Enable humanize (cloakbrowser only)")

    args = parser.parse_args()

    # Создать компоненты
    browser_mgr = BrowserManager(
        headless=args.headless,
        engine=args.engine,
        humanize=args.humanize,
        stealth="standard" if args.engine == "playwright" else None,
    )

    proxy_mgr = None
    if args.proxy_config:
        proxy_mgr = VPNProxyManager.from_yaml(args.proxy_config)

    auth_mgr = BrowserAuthManager(
        browser_manager=browser_mgr,
        db_path=args.db_path,
        session_dir=args.session_dir,
        proxy_manager=proxy_mgr,
    )

    app = create_app(
        browser_manager=browser_mgr,
        auth_manager=auth_mgr,
        proxy_manager=proxy_mgr,
        browser_engine=args.engine,
        browser_humanize=args.humanize,
    )

    logger.info(f"Starting SaaS API on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
