"""
ParsingOrchestrator — единый оркестратор парсинга для лаборатории.

Управляет очередью парсинг-задач, автоматически выбирает spider/parser
из реестра, настраивает stealth и rate limiting, обрабатывает fallback.

Использование:
    orchestrator = ParsingOrchestrator()
    result = await orchestrator.parse("https://example.com", schema="ecommerce")

Реестр источников: docs/PARSING_REGISTRY.md
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

from loguru import logger


# ─── Enums & Config ──────────────────────────────────────────────────────────

class ParsePriority(int, Enum):
    """Приоритет парсинг-задачи."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class ParseStatus(str, Enum):
    """Статус парсинг-задачи."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CACHED = "cached"
    SKIPPED = "skipped"


class StealthLevel(str, Enum):
    """Уровень антидетекта."""
    NONE = "none"
    MINIMAL = "minimal"
    STANDARD = "standard"
    ADVANCED = "advanced"
    FULL = "full"


class ParserType(str, Enum):
    """Тип парсера."""
    GENERIC_SPIDER = "generic_spider"
    ZAKUPKI_SPIDER = "zakupki_spider"
    AVITO_DEALER_SPIDER = "avito_dealer_spider"
    AUTO_PARTS_SPIDER = "auto_parts_spider"
    DATA_PARSER = "data_parser"
    PRICE_PARSER = "price_parser"
    LLM_PARSER = "llm_parser"
    SITE_HEALTH_MONITOR = "site_health_monitor"


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ParseTask:
    """Одна парсинг-задача."""
    url: str
    parser_type: ParserType | None = None
    schema: str = ""
    priority: ParsePriority = ParsePriority.NORMAL
    stealth_level: StealthLevel = StealthLevel.STANDARD
    max_pages: int = 50
    timeout: int = 60
    use_cache: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cache_key(self) -> str:
        """Ключ для кэширования."""
        key_data = f"{self.url}:{self.schema}:{self.parser_type}:{self.max_pages}"
        return hashlib.md5(key_data.encode()).hexdigest()

    @property
    def domain(self) -> str:
        parsed = urlparse(self.url)
        return parsed.netloc


@dataclass
class ParseResult:
    """Результат парсинга."""
    task: ParseTask
    status: ParseStatus
    data: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    items_count: int = 0
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "items_count": self.items_count,
            "duration_seconds": self.duration_seconds,
            "cached": self.cached,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }


@dataclass
class ParsingMetrics:
    """Метрики парсинга."""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    cached: int = 0
    total_items: int = 0
    total_duration: float = 0.0
    errors_by_type: dict[str, int] = field(default_factory=dict)
    requests_by_domain: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful / self.total_requests * 100

    @property
    def avg_duration(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_duration / self.total_requests

    def to_prometheus(self) -> str:
        """Экспорт в формате Prometheus."""
        lines = [
            "# HELP parse_requests_total Total parse requests",
            "# TYPE parse_requests_total counter",
            f'parse_requests_total{{status="success"}} {self.successful}',
            f'parse_requests_total{{status="failed"}} {self.failed}',
            f'parse_requests_total{{status="cached"}} {self.cached}',
            "",
            "# HELP parse_items_total Total items parsed",
            "# TYPE parse_items_total counter",
            f"parse_items_total {self.total_items}",
            "",
            "# HELP parse_duration_seconds Total parse duration",
            "# TYPE parse_duration_seconds counter",
            f"parse_duration_seconds {self.total_duration:.2f}",
            "",
            "# HELP parse_success_rate Success rate percentage",
            "# TYPE parse_success_rate gauge",
            f"parse_success_rate {self.success_rate:.1f}",
        ]
        for domain, count in self.requests_by_domain.items():
            lines.append(f'parse_requests_by_domain{{domain="{domain}"}} {count}')
        return "\n".join(lines)


# ─── Source Registry ──────────────────────────────────────────────────────────

# Реестр источников (генерируется из docs/PARSING_REGISTRY.md)
SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "zakupki.gov.ru": {
        "parser_type": ParserType.ZAKUPKI_SPIDER,
        "stealth_level": StealthLevel.ADVANCED,
        "rate_limit_delay": 3.0,
        "requires_proxy": True,
        "item_type": "ScrapedContract",
        "description": "Госзакупки 44-ФЗ / 223-ФЗ",
    },
    "avito.ru": {
        "parser_type": ParserType.AVITO_DEALER_SPIDER,
        "stealth_level": StealthLevel.STANDARD,
        "rate_limit_delay": 2.0,
        "requires_proxy": False,
        "item_type": "ScrapedAuto",
        "description": "Автообъявления (дилеры)",
    },
    "default": {
        "parser_type": ParserType.DATA_PARSER,
        "stealth_level": StealthLevel.STANDARD,
        "rate_limit_delay": 1.5,
        "requires_proxy": False,
        "item_type": "ScrapedPage",
        "description": "Универсальный парсинг",
    },
}

# Маппинг ниш к типам парсеров
NICHE_TO_PARSER: dict[str, ParserType] = {
    "ecommerce": ParserType.DATA_PARSER,
    "news": ParserType.DATA_PARSER,
    "realty": ParserType.DATA_PARSER,
    "medtech": ParserType.DATA_PARSER,
    "jobs": ParserType.DATA_PARSER,
    "auto": ParserType.AVITO_DEALER_SPIDER,
    "habr": ParserType.DATA_PARSER,
    "vcru": ParserType.DATA_PARSER,
    "twitter": ParserType.DATA_PARSER,
    "telegram": ParserType.DATA_PARSER,
    "zakupki": ParserType.ZAKUPKI_SPIDER,
    "auto_parts": ParserType.AUTO_PARTS_SPIDER,
    "price": ParserType.PRICE_PARSER,
    "generic": ParserType.GENERIC_SPIDER,
}


# ─── ParsingOrchestrator ─────────────────────────────────────────────────────

class ParsingOrchestrator:
    """
    Единый оркестратор парсинга.

    Управляет очередью задач, выбирает парсер по реестру,
    настраивает stealth и rate limiting, кэширует результаты.
    """

    def __init__(
        self,
        cache_ttl: int = 3600,
        max_concurrent: int = 5,
        default_stealth: StealthLevel = StealthLevel.STANDARD,
    ):
        self._cache: dict[str, ParseResult] = {}
        self._cache_ttl = cache_ttl
        self._max_concurrent = max_concurrent
        self._default_stealth = default_stealth
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._metrics = ParsingMetrics()
        self._rate_limit_last: dict[str, float] = {}

        logger.info(
            f"ParsingOrchestrator initialized: "
            f"cache_ttl={cache_ttl}s, max_concurrent={max_concurrent}"
        )

    async def parse(
        self,
        url: str,
        schema: str = "",
        priority: ParsePriority = ParsePriority.NORMAL,
        stealth_level: StealthLevel | None = None,
        max_pages: int = 50,
        timeout: int = 60,
        use_cache: bool = True,
        parser_type: ParserType | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ParseResult:
        """
        Спарсить URL с автоматическим выбором парсера.

        Args:
            url: URL для парсинга
            schema: Название схемы (ecommerce, news, zakupki, etc.)
            priority: Приоритет задачи
            stealth_level: Уровень антидетекта
            max_pages: Макс. страниц
            timeout: Таймаут в секундах
            use_cache: Использовать кэш
            parser_type: Принудительный тип парсера
            metadata: Дополнительные метаданные

        Returns:
            ParseResult с данными и метаданными
        """
        domain = urlparse(url).netloc

        # Определяем тип парсера
        if parser_type is None:
            parser_type = self._resolve_parser(domain, schema)

        # Определяем stealth level
        if stealth_level is None:
            stealth_level = self._resolve_stealth(domain)

        # Создаём задачу
        task = ParseTask(
            url=url,
            parser_type=parser_type,
            schema=schema,
            priority=priority,
            stealth_level=stealth_level,
            max_pages=max_pages,
            timeout=timeout,
            use_cache=use_cache,
            metadata=metadata or {},
        )

        # Проверяем кэш
        if use_cache and task.cache_key in self._cache:
            cached = self._cache[task.cache_key]
            cached_age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(cached.timestamp)
            ).total_seconds()
            if cached_age < self._cache_ttl:
                logger.info(f"[CACHE HIT] {url} (age={cached_age:.0f}s)")
                self._metrics.cached += 1
                cached.cached = True
                return cached
            else:
                del self._cache[task.cache_key]

        # Rate limiting
        await self._apply_rate_limit(domain)

        # Запускаем парсинг
        start_time = time.monotonic()
        self._metrics.total_requests += 1
        self._metrics.requests_by_domain[domain] = (
            self._metrics.requests_by_domain.get(domain, 0) + 1
        )

        try:
            async with self._semaphore:
                result = await self._execute_parser(task)

            result.duration_seconds = time.monotonic() - start_time
            self._metrics.total_duration += result.duration_seconds
            self._metrics.total_items += result.items_count

            if result.status == ParseStatus.SUCCESS:
                self._metrics.successful += 1
            else:
                self._metrics.failed += 1
                error_type = result.errors[0][:50] if result.errors else "unknown"
                self._metrics.errors_by_type[error_type] = (
                    self._metrics.errors_by_type.get(error_type, 0) + 1
                )

            # Кэшируем успешный результат
            if result.status == ParseStatus.SUCCESS and use_cache:
                self._cache[task.cache_key] = result

            logger.info(
                f"[PARSE] {url} → {result.status.value} "
                f"({result.items_count} items, {result.duration_seconds:.1f}s)"
            )
            return result

        except Exception as e:
            duration = time.monotonic() - start_time
            self._metrics.failed += 1
            self._metrics.total_duration += duration
            error_msg = f"{type(e).__name__}: {str(e)[:100]}"
            self._metrics.errors_by_type[error_msg] = (
                self._metrics.errors_by_type.get(error_msg, 0) + 1
            )
            logger.error(f"[PARSE ERROR] {url}: {error_msg}")
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[error_msg],
                duration_seconds=duration,
            )

    async def parse_batch(
        self,
        urls: list[str],
        schema: str = "",
        priority: ParsePriority = ParsePriority.NORMAL,
        **kwargs: Any,
    ) -> list[ParseResult]:
        """Парсить несколько URL параллельно."""
        tasks = [
            self.parse(url, schema=schema, priority=priority, **kwargs)
            for url in urls
        ]
        return await asyncio.gather(*tasks)

    def get_metrics(self) -> ParsingMetrics:
        """Получить текущие метрики."""
        return self._metrics

    def get_prometheus_metrics(self) -> str:
        """Метрики в формате Prometheus."""
        return self._metrics.to_prometheus()

    def clear_cache(self) -> int:
        """Очистить кэш. Возвращает количество удалённых записей."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")
        return count

    # ─── Private Methods ───────────────────────────────────────────────────

    def _resolve_parser(self, domain: str, schema: str) -> ParserType:
        """Определить тип парсера по домену/схеме."""
        # Сначала проверяем домен в реестре
        if domain in SOURCE_REGISTRY:
            return SOURCE_REGISTRY[domain]["parser_type"]
        # Потом проверяем схему
        if schema in NICHE_TO_PARSER:
            return NICHE_TO_PARSER[schema]
        # Fallback
        return ParserType.DATA_PARSER

    def _resolve_stealth(self, domain: str) -> StealthLevel:
        """Определить уровень антидетекта по домену."""
        if domain in SOURCE_REGISTRY:
            return SOURCE_REGISTRY[domain]["stealth_level"]
        return self._default_stealth

    async def _apply_rate_limit(self, domain: str) -> None:
        """Применить rate limiting по домену."""
        if domain in SOURCE_REGISTRY:
            delay = SOURCE_REGISTRY[domain].get("rate_limit_delay", 1.5)
        else:
            delay = 1.5

        last_request = self._rate_limit_last.get(domain, 0)
        elapsed = time.monotonic() - last_request
        if elapsed < delay:
            wait = delay - elapsed
            logger.debug(f"[RATE LIMIT] {domain}: waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        self._rate_limit_last[domain] = time.monotonic()

    async def _execute_parser(self, task: ParseTask) -> ParseResult:
        """Запустить конкретный парсер с LLM fallback."""
        parser_map: dict[ParserType, Callable] = {
            ParserType.GENERIC_SPIDER: self._run_generic_spider,
            ParserType.ZAKUPKI_SPIDER: self._run_zakupki_spider,
            ParserType.AVITO_DEALER_SPIDER: self._run_avito_spider,
            ParserType.AUTO_PARTS_SPIDER: self._run_auto_parts_spider,
            ParserType.DATA_PARSER: self._run_data_parser,
            ParserType.PRICE_PARSER: self._run_price_parser,
            ParserType.LLM_PARSER: self._run_llm_parser,
            ParserType.SITE_HEALTH_MONITOR: self._run_site_monitor,
        }

        runner = parser_map.get(task.parser_type)
        if runner is None:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"Unknown parser type: {task.parser_type}"],
            )

        result = await runner(task)

        # LLM Fallback: если spider/парсер вернул 0 результатов,
        # автоматически пробуем SelfHealingParser
        if (
            result.status == ParseStatus.FAILED
            or result.items_count == 0
        ) and task.parser_type not in (
            ParserType.LLM_PARSER,
            ParserType.SITE_HEALTH_MONITOR,
        ):
            logger.info(
                f"[LLM FALLBACK] {task.parser_type.value} returned 0 items "
                f"for {task.url} — trying SelfHealingParser"
            )
            from lab_playwright_kit.llm_parse import SelfHealingParser

            llm_result = await self._run_self_healing_parser(task)
            if llm_result.status == ParseStatus.SUCCESS:
                # Мержим информацию о fallback
                llm_result.errors.append(
                    f"[LLM_FALLBACK] triggered after {task.parser_type.value} "
                    f"returned {result.items_count} items"
                )
                return llm_result

        return result

    async def _run_generic_spider(self, task: ParseTask) -> ParseResult:
        """Запуск GenericSpider."""
        try:
            from lab_playwright_kit.scrapy_engine.spiders.generic_spider import GenericSpider
            # GenericSpider — Scrapy spider, требует CrawlerProcess
            # Для асинхронного вызова используем subprocess
            import subprocess
            import tempfile

            output_file = tempfile.mktemp(suffix=".json")
            cmd = [
                "python3", "-m", "scrapy", "crawl", "generic",
                "-a", f"url={task.url}",
                "-a", f"max_pages={task.max_pages}",
                "-o", output_file,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd="/root/LabDoctorM/projects/lab-playwright-expert",
                env={"PYTHONPATH": "src", "PATH": "/usr/bin:/usr/local/bin"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=task.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=["Timeout"],
                )

            if proc.returncode != 0:
                error = stderr.decode()[:200] if stderr else "Unknown error"
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=[f"Scrapy error: {error}"],
                )

            # Читаем результат
            try:
                with open(output_file) as f:
                    data = json.load(f)
                import os
                os.unlink(task_url)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []

            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"GenericSpider error: {str(e)[:200]}"],
            )

    async def _run_zakupki_spider(self, task: ParseTask) -> ParseResult:
        """Запуск ZakupkiSpider."""
        try:
            from lab_playwright_kit.scrapy_engine.spiders.zakupki_spider import ZakupkiSpider
            # Аналогично — subprocess + scrapy crawl
            import subprocess
            import tempfile

            output_file = tempfile.mktemp(suffix=".json")
            cmd = [
                "python3", "-m", "scrapy", "crawl", "zakupki",
                "-a", f"url={task.url}",
                "-a", f"max_pages={task.max_pages}",
                "-o", output_file,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd="/root/LabDoctorM/projects/lab-playwright-expert",
                env={"PYTHONPATH": "src", "PATH": "/usr/bin:/usr/local/bin"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=task.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=["Timeout"],
                )

            if proc.returncode != 0:
                error = stderr.decode()[:200] if stderr else "Unknown error"
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=[f"Scrapy error: {error}"],
                )

            try:
                with open(output_file) as f:
                    data = json.load(f)
                import os
                os.unlink(output_file)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []

            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"ZakupkiSpider error: {str(e)[:200]}"],
            )

    async def _run_avito_spider(self, task: ParseTask) -> ParseResult:
        """Запуск AvitoDealerSpider (standalone режим через BeautifulSoup)."""
        try:
            import httpx
            from lab_playwright_kit.scrapy_engine.spiders.avito_dealer_spider import (
                parse_avito_listing,
            )

            async with httpx.AsyncClient(
                timeout=task.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            ) as client:
                response = await client.get(task.url)
                if response.status_code != 200:
                    return ParseResult(
                        task=task,
                        status=ParseStatus.FAILED,
                        errors=[f"HTTP {response.status_code}"],
                    )
                data = parse_avito_listing(response.text, task.url)

            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"AvitoDealerSpider error: {str(e)[:200]}"],
            )

    async def _run_auto_parts_spider(self, task: ParseTask) -> ParseResult:
        """Запуск PlaywrightPartSpider."""
        try:
            from lab_playwright_kit.scrapy_engine.spiders.auto_parts.part_spider import (
                PlaywrightPartSpider,
            )
            # PlaywrightPartSpider требует Scrapy CrawlerProcess + Playwright
            # Используем subprocess
            import subprocess
            import tempfile

            output_file = tempfile.mktemp(suffix=".json")
            cmd = [
                "python3", "-m", "scrapy", "crawl", "auto_parts",
                "-a", f"url={task.url}",
                "-o", output_file,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd="/root/LabDoctorM/projects/lab-playwright-expert",
                env={"PYTHONPATH": "src", "PATH": "/usr/bin:/usr/local/bin"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=task.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=["Timeout"],
                )

            if proc.returncode != 0:
                error = stderr.decode()[:200] if stderr else "Unknown error"
                return ParseResult(
                    task=task,
                    status=ParseStatus.FAILED,
                    errors=[f"Scrapy error: {error}"],
                )

            try:
                with open(output_file) as f:
                    data = json.load(f)
                import os
                os.unlink(output_file)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []

            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"PlaywrightPartSpider error: {str(e)[:200]}"],
            )

    async def _run_data_parser(self, task: ParseTask) -> ParseResult:
        """Запуск DataParser через BrowserManager.
        
        Использует нативный парсинг через DataParser.parse() с адаптером
        для совместимости с текущей версией BrowserManager.
        """
        try:
            from lab_playwright_kit.data_parser import DataParser, NicheType, detect_niche
            from lab_playwright_kit.browser import BrowserManager

            # Определяем нишу
            niche_map = {
                "ecommerce": NicheType.ECOMMERCE,
                "news": NicheType.NEWS,
                "realty": NicheType.REALTY,
                "medtech": NicheType.MEDTECH,
                "jobs": NicheType.JOBS,
                "auto": NicheType.AUTO,
                "habr": NicheType.HABR,
                "vcru": NicheType.VCRU,
                "twitter": NicheType.TWITTER,
                "telegram": NicheType.TELEGRAM,
            }
            if task.schema in niche_map:
                niche = niche_map[task.schema]
            else:
                niche = detect_niche(task.url)
                if niche == NicheType.GENERIC:
                    niche = NicheType.NEWS

            start_time = time.monotonic()

            async with BrowserManager(headless=True, timeout=task.timeout * 1000) as browser_mgr:
                # DataParser._ensure_page() вызывает await self._browser_mgr.get_context()
                # Добавляем совместимый async метод если отсутствует
                if not hasattr(browser_mgr, 'get_context'):
                    _ctx = browser_mgr._context
                    async def _get_context():
                        return _ctx
                    browser_mgr.get_context = _get_context
                
                parser = DataParser(
                    browser_manager=browser_mgr,
                    niche=niche,
                    timeout=float(task.timeout),
                    max_retries=2,
                )
                result = await parser.parse(task.url, niche=niche)

            duration = time.monotonic() - start_time
            data = [result.data] if result and result.data else []
            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
                duration_seconds=duration,
                errors=result.errors if result else [],
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"DataParser error: {str(e)[:200]}"],
            )

    async def _run_price_parser(self, task: ParseTask) -> ParseResult:
        """Запуск PriceParser."""
        try:
            from lab_playwright_kit.price_parser import PriceParser

            parser = PriceParser()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, parser.parse_url, task.url
            )

            data = result if isinstance(result, list) else [result] if result else []
            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"PriceParser error: {str(e)[:200]}"],
            )

    async def _run_llm_parser(self, task: ParseTask) -> ParseResult:
        """Запуск LLMParser (fallback)."""
        try:
            from lab_playwright_kit.llm_parse import LLMParser, LLMConfig
            from lab_playwright_kit.browser import BrowserManager

            config = LLMConfig()
            parser = LLMParser(config)

            async with BrowserManager(headless=True, timeout=task.timeout * 1000) as browser:
                page = await browser.new_page()
                await page.goto(task.url, wait_until="domcontentloaded", timeout=task.timeout * 1000)
                result = await parser.extract(page, task.schema or "извлечь все данные")
                await page.close()

            data = [result] if result and result.get("found", True) else []
            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"LLMParser error: {str(e)[:200]}"],
            )

    async def _run_site_monitor(self, task: ParseTask) -> ParseResult:
        """Запуск SiteHealthMonitor."""
        try:
            from lab_playwright_kit.site_health_monitor import SiteHealthMonitor

            monitor = SiteHealthMonitor()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, monitor.check_url, task.url
            )

            data = [result] if result else []
            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"SiteHealthMonitor error: {str(e)[:200]}"],
            )


    async def _run_self_healing_parser(self, task: ParseTask) -> ParseResult:
        """Запуск SelfHealingParser как fallback."""
        try:
            from lab_playwright_kit.llm_parse import (
                LLMParser, LLMConfig, SelfHealingParser,
            )
            from lab_playwright_kit.browser import BrowserManager

            config = LLMConfig()
            llm = LLMParser(config)
            parser = SelfHealingParser(llm, max_retries=2)

            async with BrowserManager(headless=True, timeout=task.timeout * 1000) as browser:
                page = await browser.new_page()
                await page.goto(task.url, wait_until="domcontentloaded", timeout=task.timeout * 1000)
                result = await parser.extract_with_retry(
                    page, task.schema or "извлечь все данные"
                )
                await page.close()

            data = [result] if result and result.get("found", True) else []
            return ParseResult(
                task=task,
                status=ParseStatus.SUCCESS if data else ParseStatus.FAILED,
                data=data,
                items_count=len(data),
            )
        except Exception as e:
            return ParseResult(
                task=task,
                status=ParseStatus.FAILED,
                errors=[f"SelfHealingParser error: {str(e)[:200]}"],
            )


# ─── Convenience Functions ───────────────────────────────────────────────────

async def parse_url(
    url: str,
    schema: str = "",
    stealth: str = "standard",
    **kwargs: Any,
) -> ParseResult:
    """Удобная функция для быстрого парсинга."""
    orchestrator = ParsingOrchestrator()
    stealth_level = StealthLevel(stealth)
    return await orchestrator.parse(url, schema=schema, stealth_level=stealth_level, **kwargs)


async def parse_batch(
    urls: list[str],
    schema: str = "",
    **kwargs: Any,
) -> list[ParseResult]:
    """Удобная функция для пакетного парсинга."""
    orchestrator = ParsingOrchestrator()
    return await orchestrator.parse_batch(urls, schema=schema, **kwargs)
