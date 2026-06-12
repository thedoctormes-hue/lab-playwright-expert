#!/usr/bin/env python3
"""
Distributed Crawler Framework для Lab Playwright Kit.

Масштабируемый веб-краулер на базе v2.0 модулей:
  - CrawlerEngine: оркестратор задач (TaskOrchestrator)
  - PageFetcher: загрузка страниц (browser + stealth + fingerprint)
  - ContentExtractor: извлечение данных (parser + llm_parse)
  - ProxyManager: ротация прокси (proxy_rotation)
  - RateLimiter: ограничение частоты запросов (RateLimit)
  - ResultStore: хранение результатов (JSON / SQLite)

Использование:
    PYTHONPATH=src python3 scripts/distributed_crawler.py --config config.yaml
    PYTHONPATH=src python3 scripts/distributed_crawler.py --seed https://example.com --depth 2
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import yaml
from loguru import logger


# ─── Добавить src в path если ещё нет ──────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit import (
    BrowserFingerprint,
    BrowserManager,
    FingerprintManager,
    PageParser,
    ProxyRotator,
    RateLimit,
    ScreenshotMaker,
    StealthConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CrawlerConfig:
    """Конфигурация краулера — загружается из YAML или CLI-аргументов."""

    # Сиды
    seeds: list[str] = field(default_factory=lambda: ["https://example.com"])

    # Глубина и ширина
    max_depth: int = 2
    max_pages: int = 50
    max_pages_per_domain: int = 0  # 0 = без ограничений

    # Фильтрация
    allowed_domains: list[str] = field(default_factory=list)  # пусто = все
    excluded_domains: list[str] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)  # regex паттерны
    exclude_patterns: list[str] = field(default_factory=lambda: [
        r"\.(pdf|jpg|jpeg|png|gif|svg|css|js|zip|tar|gz|mp3|mp4|avi|mov|doc|docx|xls|xlsx)$",
        r"mailto:",
        r"tel:",
        r"#",
    ])

    # Rate limiting
    requests_per_second: float = 1.0
    delay_range: tuple[float, float] = (1.0, 3.0)
    respect_robots_txt: bool = True
    crawl_delay_from_robots: bool = True

    # Stealth
    stealth_enabled: bool = True
    stealth_profile: str = "casual_reader"
    stealth_level: str = "standard"  # minimal, standard, advanced, full

    # Прокси
    proxy_enabled: bool = False
    proxy_file: str = "proxies.txt"
    proxy_strategy: str = "round_robin"

    # Браузер
    headless: bool = True
    browser_type: str = "chromium"
    page_timeout: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080

    # Выходные данные
    output_format: str = "json"  # json, sqlite, both, postgresql
    output_directory: str = "./crawl_output"
    save_screenshots: bool = False
    save_html: bool = False

    # PostgreSQL
    use_postgresql: bool = False
    database_url: str = "postgresql://parser:parser@localhost:5432/parser_db"

    # Оркестратор
    workers: int = 3

    # Поведение
    follow_redirects: bool = True
    retry_failed: bool = True
    max_retries: int = 2
    retry_delay: float = 5.0

    # Дедупликация
    dedup_content: bool = True  # дедупликация по хэшу контента

    # Sitemap
    parse_sitemap: bool = True

    # Логирование
    verbose: bool = False
    log_file: str = ""

    @classmethod
    def from_yaml(cls, path: str) -> CrawlerConfig:
        """Загрузить конфигурацию из YAML-файла."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        # Сиды
        if "seeds" in data:
            config.seeds = data["seeds"]

        # Глубина
        if "max_depth" in data:
            config.max_depth = int(data["max_depth"])
        if "max_pages" in data:
            config.max_pages = int(data["max_pages"])
        if "max_pages_per_domain" in data:
            config.max_pages_per_domain = int(data["max_pages_per_domain"])

        # Фильтрация
        if "allowed_domains" in data:
            config.allowed_domains = data["allowed_domains"]
        if "excluded_domains" in data:
            config.excluded_domains = data["excluded_domains"]
        if "url_patterns" in data:
            config.url_patterns = data["url_patterns"]
        if "exclude_patterns" in data:
            config.exclude_patterns = data["exclude_patterns"]

        # Rate limiting
        if "rate_limit" in data:
            rl = data["rate_limit"]
            if "requests_per_second" in rl:
                config.requests_per_second = float(rl["requests_per_second"])
            if "delay_range" in rl:
                config.delay_range = tuple(rl["delay_range"])
            if "respect_robots_txt" in rl:
                config.respect_robots_txt = bool(rl["respect_robots_txt"])

        # Stealth
        if "stealth" in data:
            st = data["stealth"]
            if "enabled" in st:
                config.stealth_enabled = bool(st["enabled"])
            if "profile" in st:
                config.stealth_profile = st["profile"]
            if "level" in st:
                config.stealth_level = st["level"]

        # Прокси
        if "proxy" in data:
            px = data["proxy"]
            if "enabled" in px:
                config.proxy_enabled = bool(px["enabled"])
            if "file" in px:
                config.proxy_file = px["file"]
            if "strategy" in px:
                config.proxy_strategy = px["strategy"]

        # Браузер
        if "browser" in data:
            br = data["browser"]
            if "headless" in br:
                config.headless = bool(br["headless"])
            if "type" in br:
                config.browser_type = br["type"]
            if "timeout" in br:
                config.page_timeout = int(br["timeout"])

        # Выход
        if "output" in data:
            out = data["output"]
            if "format" in out:
                config.output_format = out["format"]
            if "directory" in out:
                config.output_directory = out["directory"]
            if "screenshots" in out:
                config.save_screenshots = bool(out["screenshots"])
            if "html" in out:
                config.save_html = bool(out["html"])

        # Оркестратор
        if "workers" in data:
            config.workers = int(data["workers"])

        # Поведение
        if "behavior" in data:
            bh = data["behavior"]
            if "retry_failed" in bh:
                config.retry_failed = bool(bh["retry_failed"])
            if "max_retries" in bh:
                config.max_retries = int(bh["max_retries"])

        # Дедупликация
        if "dedup_content" in data:
            config.dedup_content = bool(data["dedup_content"])

        # Sitemap
        if "parse_sitemap" in data:
            config.parse_sitemap = bool(data["parse_sitemap"])

        # Логирование
        if "verbose" in data:
            config.verbose = bool(data["verbose"])
        if "log_file" in data:
            config.log_file = data["log_file"]

        return config

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> CrawlerConfig:
        """Создать конфигурацию из CLI-аргументов."""
        config = cls()

        if args.config:
            config = cls.from_yaml(args.config)

        # CLI аргументы переопределяют YAML
        if args.seed:
            config.seeds = [args.seed]
        if args.depth is not None:
            config.max_depth = args.depth
        if args.output:
            config.output_directory = args.output
        if args.stealth:
            config.stealth_enabled = True
        if args.verbose:
            config.verbose = True
        if args.workers:
            config.workers = args.workers
        if args.max_pages:
            config.max_pages = args.max_pages
        if args.proxy:
            config.proxy_enabled = True
            config.proxy_file = args.proxy
        if args.headless is not None:
            config.headless = args.headless

        return config


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ResultStore — хранение результатов
# ═══════════════════════════════════════════════════════════════════════════════

class ResultStore:
    """Хранилище результатов краулинга — JSON, SQLite и/или PostgreSQL."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.output_dir = Path(config.output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._json_file = self.output_dir / "crawl_results.json"
        self._results: list[dict[str, Any]] = []

        # SQLite
        self._db_path = str(self.output_dir / "crawl_results.db")
        self._db: sqlite3.Connection | None = None

        # PostgreSQL
        self._pg_conn = None

        if config.output_format in ("sqlite", "both"):
            self._init_sqlite()

        if config.use_postgresql or config.output_format == "postgresql":
            self._init_postgresql()

    def _init_postgresql(self) -> None:
        """Инициализировать PostgreSQL подключение."""
        try:
            import psycopg2
            self._pg_conn = psycopg2.connect(self.config.database_url)
            self._pg_conn.autocommit = False

            with self._pg_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pages (
                        id TEXT PRIMARY KEY,
                        url TEXT UNIQUE NOT NULL,
                        domain TEXT NOT NULL,
                        title TEXT,
                        text_content TEXT,
                        links JSONB,
                        images JSONB,
                        meta JSONB,
                        structured JSONB,
                        depth INTEGER,
                        status_code INTEGER,
                        content_hash TEXT,
                        crawled_at DOUBLE PRECISION,
                        screenshot_path TEXT,
                        html_path TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pg_pages_domain ON pages(domain)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pg_pages_url ON pages(url)
                """)
            self._pg_conn.commit()
            logger.info("PostgreSQL initialized")
        except ImportError:
            logger.warning("psycopg2 not installed, PostgreSQL disabled")
            self._pg_conn = None
        except Exception as e:
            logger.error(f"PostgreSQL init error: {e}")
            self._pg_conn = None

    def _init_sqlite(self) -> None:
        """Инициализировать SQLite базу."""
        self._db = sqlite3.connect(self._db_path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                domain TEXT NOT NULL,
                title TEXT,
                text_content TEXT,
                links TEXT,
                images TEXT,
                meta TEXT,
                structured TEXT,
                depth INTEGER,
                status_code INTEGER,
                content_hash TEXT,
                crawled_at REAL,
                screenshot_path TEXT,
                html_path TEXT
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS crawl_stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_pages_depth ON pages(depth)
        """)
        self._db.commit()
        logger.info(f"SQLite initialized: {self._db_path}")

    def add_result(self, result: dict[str, Any]) -> None:
        """Добавить результат краулинга."""
        self._results.append(result)

        if self._db:
            self._save_to_sqlite(result)

        if self._pg_conn:
            self._save_to_postgresql(result)

    def _save_to_sqlite(self, result: dict[str, Any]) -> None:
        """Сохранить результат в SQLite."""
        try:
            self._db.execute(
                """
                INSERT OR REPLACE INTO pages
                (id, url, domain, title, text_content, links, images, meta,
                 structured, depth, status_code, content_hash, crawled_at,
                 screenshot_path, html_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("id", str(uuid.uuid4())),
                    result.get("url", ""),
                    result.get("domain", ""),
                    result.get("title", ""),
                    result.get("text_content", "")[:50000],  # limit
                    json.dumps(result.get("links", []), ensure_ascii=False)[:10000],
                    json.dumps(result.get("images", []), ensure_ascii=False)[:5000],
                    json.dumps(result.get("meta", {}), ensure_ascii=False)[:5000],
                    json.dumps(result.get("structured", {}), ensure_ascii=False)[:5000],
                    result.get("depth", 0),
                    result.get("status_code", 0),
                    result.get("content_hash", ""),
                    result.get("crawled_at", time.time()),
                    result.get("screenshot_path", ""),
                    result.get("html_path", ""),
                ),
            )
            self._db.commit()
        except Exception as e:
            logger.error(f"SQLite save error: {e}")

    def _save_to_postgresql(self, result: dict[str, Any]) -> None:
        """Сохранить результат в PostgreSQL."""
        if not self._pg_conn:
            return
        try:
            import psycopg2.extras
            with self._pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pages
                    (id, url, domain, title, text_content, links, images,
                     meta, structured, depth, status_code, content_hash,
                     crawled_at, screenshot_path, html_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        text_content = EXCLUDED.text_content,
                        links = EXCLUDED.links,
                        images = EXCLUDED.images,
                        meta = EXCLUDED.meta,
                        structured = EXCLUDED.structured,
                        content_hash = EXCLUDED.content_hash,
                        crawled_at = EXCLUDED.crawled_at
                    """,
                    (
                        result.get("id", str(uuid.uuid4())),
                        result.get("url", ""),
                        result.get("domain", ""),
                        result.get("title", ""),
                        result.get("text_content", "")[:50000],
                        json.dumps(result.get("links", [])),
                        json.dumps(result.get("images", [])),
                        json.dumps(result.get("meta", {})),
                        json.dumps(result.get("structured", {})),
                        result.get("depth", 0),
                        result.get("status_code", 0),
                        result.get("content_hash", ""),
                        result.get("crawled_at", time.time()),
                        result.get("screenshot_path", ""),
                        result.get("html_path", ""),
                    ),
                )
            self._pg_conn.commit()
        except Exception as e:
            logger.error(f"PostgreSQL save error: {e}")
            try:
                self._pg_conn.rollback()
            except Exception:
                pass

    def save_json(self) -> str:
        """Сохранить все результаты в JSON-файл."""
        output = {
            "crawl_info": {
                "started_at": self._results[0].get("crawled_at", 0) if self._results else 0,
                "finished_at": time.time(),
                "total_pages": len(self._results),
                "domains": list(set(r.get("domain", "") for r in self._results)),
            },
            "results": self._results,
        }

        with open(self._json_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON saved: {self._json_file} ({len(self._results)} pages)")
        return str(self._json_file)

    def save_stats(self, stats: dict[str, Any]) -> None:
        """Сохранить статистику краулинга."""
        if self._db:
            for key, value in stats.items():
                self._db.execute(
                    "INSERT OR REPLACE INTO crawl_stats (key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)),
                )
            self._db.commit()

        # Также сохранить в JSON
        stats_file = self.output_dir / "crawl_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    def close(self) -> None:
        """Закрыть соединения."""
        if self._db:
            self._db.close()
        if self._pg_conn:
            self._pg_conn.close()

    @property
    def total_saved(self) -> int:
        return len(self._results)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ProxyManager — ротация прокси
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyManager:
    """Менеджер прокси на базе ProxyRotator."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._rotator: ProxyRotator | None = None
        self._loaded = False

    def load(self) -> bool:
        """Загрузить прокси из файла."""
        if not self.config.proxy_enabled:
            logger.info("Proxy disabled")
            return False

        proxy_file = Path(self.config.proxy_file)
        if not proxy_file.exists():
            logger.warning(f"Proxy file not found: {proxy_file}")
            return False

        self._rotator = ProxyRotator(strategy=self.config.proxy_strategy)

        count = 0
        with open(proxy_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    self._rotator.add_proxy(line)
                    count += 1
                except Exception as e:
                    logger.warning(f"Invalid proxy line '{line}': {e}")

        self._loaded = count > 0
        logger.info(f"Loaded {count} proxies")
        return self._loaded

    def get_proxy(self) -> dict | None:
        """Получить следующий прокси в формате Playwright."""
        if not self._rotator:
            return None
        proxy = self._rotator.get_next()
        if proxy:
            return proxy.playwright_format
        return None

    def mark_success(self, proxy_dict: dict) -> None:
        """Пометить прокси как успешный."""
        if self._rotator and proxy_dict:
            url = proxy_dict.get("server", "")
            for p in self._rotator.proxies:
                if p.url == url:
                    self._rotator.mark_success(p)
                    break

    def mark_failed(self, proxy_dict: dict) -> None:
        """Пометить прокси как неуспешный."""
        if self._rotator and proxy_dict:
            url = proxy_dict.get("server", "")
            for p in self._rotator.proxies:
                if p.url == url:
                    self._rotator.mark_failed(p)
                    break

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def stats(self) -> dict:
        if self._rotator:
            return self._rotator.get_stats()
        return {"total": 0, "healthy": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RateLimiter — ограничение частоты запросов
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Rate limiter по доменам на базе TaskOrchestrator.RateLimit."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._limits: dict[str, RateLimit] = {}
        self._default_limit = RateLimit(
            platform="default",
            max_per_minute=int(config.requests_per_second * 60),
            cooldown_seconds=1.0 / max(config.requests_per_second, 0.01),
        )

    def _get_limit(self, domain: str) -> RateLimit:
        """Получить rate limit для домена."""
        if domain not in self._limits:
            self._limits[domain] = RateLimit(
                platform=domain,
                max_per_minute=int(self.config.requests_per_second * 60),
                cooldown_seconds=1.0 / max(self.config.requests_per_second, 0.01),
            )
        return self._limits[domain]

    async def acquire(self, domain: str) -> None:
        """Дождаться разрешения на запрос к домену."""
        limit = self._get_limit(domain)
        while not limit.can_execute():
            wait = limit.wait_time
            logger.debug(f"Rate limit wait for {domain}: {wait:.1f}s")
            await asyncio.sleep(wait)
        limit.record_action()

    async def delay(self) -> None:
        """Случайная задержка между запросами."""
        import random
        delay = random.uniform(*self.config.delay_range)
        await asyncio.sleep(delay)

    def update_from_robots(self, domain: str, crawl_delay: float) -> None:
        """Обновить rate limit на основе robots.txt Crawl-delay."""
        if self.config.crawl_delay_from_robots and crawl_delay > 0:
            limit = self._get_limit(domain)
            limit.cooldown_seconds = max(limit.cooldown_seconds, crawl_delay)
            logger.info(f"Rate limit for {domain} updated from robots.txt: {crawl_delay}s")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RobotsHandler — парсинг robots.txt и sitemap.xml
# ═══════════════════════════════════════════════════════════════════════════════

class RobotsHandler:
    """Обработчик robots.txt и sitemap.xml."""

    def __init__(self, respect_robots: bool = True, parse_sitemap: bool = True):
        self.respect_robots = respect_robots
        self.parse_sitemap = parse_sitemap
        self._parsers: dict[str, RobotFileParser] = {}
        self._sitemaps: dict[str, list[str]] = {}
        self._cache_domains: set[str] = set()

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Проверить разрешение на краулинг из robots.txt."""
        if not self.respect_robots:
            return True

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._parsers:
            await self._load_robots(domain, user_agent)

        parser = self._parsers.get(domain)
        if parser:
            return parser.can_fetch(user_agent, url)
        return True

    async def _load_robots(self, domain: str, user_agent: str) -> None:
        """Загрузить и распарсить robots.txt."""
        import httpx

        robots_url = f"{domain}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(robots_url)

            parser = RobotFileParser()
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                # Если robots.txt не найден — разрешаем всё
                parser.parse([])
            self._parsers[domain] = parser

            # Извлечь sitemap URLs
            if self.parse_sitemap:
                sitemap_urls = []
                for line in response.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        s_url = line.split(":", 1)[1].strip()
                        sitemap_urls.append(s_url)
                if sitemap_urls:
                    self._sitemaps[domain] = sitemap_urls

            # Crawl-delay
            for line in response.text.splitlines():
                if "crawl-delay" in line.lower():
                    try:
                        float(line.split(":")[1].strip())
                    except (ValueError, IndexError):
                        pass

            logger.info(f"robots.txt loaded for {domain}: {len(parser.entries)} rules, sitemaps={len(self._sitemaps.get(domain, []))}")

        except Exception as e:
            logger.debug(f"Failed to load robots.txt for {domain}: {e}")
            self._parsers[domain] = RobotFileParser()
            self._parsers[domain].parse([])

    async def get_sitemap_urls(self, domain: str) -> list[str]:
        """Получить URL из sitemap.xml домена."""
        if not self.parse_sitemap:
            return []

        sitemap_urls = self._sitemaps.get(domain, [])
        if not sitemap_urls:
            return []

        import httpx
        all_urls = []
        for sitemap_url in sitemap_urls:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(sitemap_url)
                if response.status_code == 200:
                    # Простой парсинг XML
                    import re
                    urls = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", response.text)
                    all_urls.extend(urls)
            except Exception as e:
                logger.debug(f"Failed to parse sitemap {sitemap_url}: {e}")

        logger.info(f"Sitemap for {domain}: {len(all_urls)} URLs extracted")
        return all_urls

    def get_crawl_delay(self, domain: str) -> float | None:
        """Получить Crawl-delay из robots.txt."""
        parser = self._parsers.get(domain)
        if parser:
            try:
                return parser.crawl_delay("*")
            except AttributeError:
                pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PageFetcher — загрузка страниц со стелсом
# ═══════════════════════════════════════════════════════════════════════════════

class PageFetcher:
    """Загрузчик страниц с stealth-маскировкой и fingerprint."""

    def __init__(self, config: CrawlerConfig, proxy_manager: ProxyManager):
        self.config = config
        self.proxy_manager = proxy_manager
        self._browser_manager: BrowserManager | None = None
        self._fingerprint: BrowserFingerprint | None = None
        self._stealth_config: StealthConfig | None = None

    async def start(self) -> None:
        """Инициализировать браузер и stealth."""
        # Генерировать fingerprint
        self._fingerprint = FingerprintManager.generate(
            profile_name=f"crawler_{uuid.uuid4().hex[:8]}",
            os="windows",
            browser="chrome",
        )

        # Stealth config
        stealth_level = self.config.stealth_level
        if stealth_level == "minimal":
            self._stealth_config = StealthConfig.minimal()
        elif stealth_level == "standard":
            self._stealth_config = StealthConfig.standard()
        elif stealth_level == "advanced":
            self._stealth_config = StealthConfig.advanced()
        elif stealth_level == "full":
            self._stealth_config = StealthConfig.full()
        else:
            self._stealth_config = StealthConfig.standard()

        if not self.config.stealth_enabled:
            self._stealth_config = StealthConfig.minimal()
            self._stealth_config.enabled = False

        # Прокси
        proxy = self.proxy_manager.get_proxy() if self.proxy_manager.is_loaded else None

        # Браузер
        self._browser_manager = BrowserManager(
            headless=self.config.headless,
            browser_type=self.config.browser_type,
            user_agent=self._fingerprint.user_agent,
            proxy=proxy,
            timeout=self.config.page_timeout,
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        )

        await self._browser_manager.start()
        logger.info(f"PageFetcher started: UA={self._fingerprint.user_agent[:60]}...")

    async def stop(self) -> None:
        """Остановить браузер."""
        if self._browser_manager:
            await self._browser_manager.stop()
            logger.info("PageFetcher stopped")

    async def fetch(self, url: str) -> tuple[Any | None, dict[str, Any]]:
        """Загрузить страницу и вернуть (page, metadata).

        Returns:
            (page, metadata) — page=None если ошибка
        """
        if not self._browser_manager:
            raise RuntimeError("PageFetcher not started")

        metadata: dict[str, Any] = {
            "url": url,
            "fetched_at": time.time(),
            "proxy_used": None,
            "error": None,
        }

        try:
            page = await self._browser_manager.new_page()

            # Применить stealth
            if self._stealth_config and self._stealth_config.enabled:
                await self._apply_stealth(page)

            # Применить fingerprint
            if self._fingerprint:
                await FingerprintManager.apply(page, self._fingerprint)

            # Навигация
            response = await page.goto(url, wait_until="domcontentloaded")
            metadata["status_code"] = response.status if response else 0

            # Ждём загрузки JavaScript
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # таймаут networkidle — не критично

            metadata["final_url"] = page.url
            metadata["title"] = await page.title()

            return page, metadata

        except Exception as e:
            metadata["error"] = str(e)
            logger.error(f"Fetch error for {url}: {e}")
            return None, metadata

    async def _apply_stealth(self, page) -> None:
        """Применить stealth-скрипты к странице."""
        if not self._stealth_config:
            return

        scripts = self._stealth_config.get_scripts()
        for script in scripts:
            try:
                await page.add_init_script(script)
            except Exception as e:
                logger.debug(f"Stealth script injection error: {e}")

    async def take_screenshot(self, page, url: str, output_dir: Path) -> str:
        """Сделать скриншот страницы."""
        maker = ScreenshotMaker(str(output_dir / "screenshots"))
        safe_name = hashlib.md5(url.encode()).hexdigest()[:12]
        return await maker.full_page(page, prefix=f"page_{safe_name}")

    async def save_html(self, page, url: str, output_dir: Path) -> str:
        """Сохранить HTML страницы."""
        html_dir = output_dir / "html"
        html_dir.mkdir(exist_ok=True)
        safe_name = hashlib.md5(url.encode()).hexdigest()[:12]
        html_path = html_dir / f"page_{safe_name}.html"
        content = await page.content()
        html_path.write_text(content, encoding="utf-8")
        return str(html_path)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ContentExtractor — извлечение данных
# ═══════════════════════════════════════════════════════════════════════════════

class ContentExtractor:
    """Извлечение структурированных данных из страниц."""

    def __init__(self, config: CrawlerConfig):
        self.config = config

    async def extract(self, page, url: str, depth: int) -> dict[str, Any]:
        """Извлечь данные из страницы.

        Returns:
            Словарь с извлечёнными данными
        """
        parser = PageParser(page)

        try:
            content = await parser.parse()
        except Exception as e:
            logger.error(f"Parse error for {url}: {e}")
            return self._empty_result(url, depth, error=str(e))

        # Дедупликация контента
        content_hash = ""
        if self.config.dedup_content and content.text:
            content_hash = hashlib.md5(
                content.text.strip().encode()
            ).hexdigest()

        result = {
            "id": str(uuid.uuid4()),
            "url": url,
            "domain": content.domain,
            "title": content.title,
            "text_content": content.text[:50000],  # лимит
            "links": content.links[:500],  # лимит
            "images": content.images[:100],
            "meta": content.meta,
            "structured": content.structured,
            "depth": depth,
            "content_hash": content_hash,
            "crawled_at": time.time(),
            "text_length": len(content.text),
            "links_count": len(content.links),
            "images_count": len(content.images),
        }

        return result

    def _empty_result(self, url: str, depth: int, error: str = "") -> dict[str, Any]:
        """Пустой результат при ошибке."""
        from urllib.parse import urlparse
        return {
            "id": str(uuid.uuid4()),
            "url": url,
            "domain": urlparse(url).netloc,
            "title": "",
            "text_content": "",
            "links": [],
            "images": [],
            "meta": {},
            "structured": {},
            "depth": depth,
            "content_hash": "",
            "crawled_at": time.time(),
            "text_length": 0,
            "links_count": 0,
            "images_count": 0,
            "error": error,
        }

    def extract_links(self, result: dict[str, Any]) -> list[str]:
        """Извлечь абсолютные URL из результата."""
        return [link.get("href", "") for link in result.get("links", []) if link.get("href")]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. URL Filter — фильтрация URL
# ═══════════════════════════════════════════════════════════════════════════════

class URLFilter:
    """Фильтр URL для краулинга."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        import re
        self._exclude_patterns = [re.compile(p, re.IGNORECASE) for p in config.exclude_patterns]
        self._url_patterns = [re.compile(p, re.IGNORECASE) for p in config.url_patterns] if config.url_patterns else []

    def should_crawl(self, url: str, current_depth: int) -> bool:
        """Проверить, нужно ли краулить URL."""
        # Глубина
        if current_depth >= self.config.max_depth:
            return False

        parsed = urlparse(url)

        # Только http/https
        if parsed.scheme not in ("http", "https"):
            return False

        # Исключённые домены
        domain = parsed.netloc.lower()
        for excluded in self.config.excluded_domains:
            if excluded.lower() in domain:
                return False

        # Разрешённые домены (если указаны)
        if self.config.allowed_domains:
            allowed = any(
                d.lower() in domain for d in self.config.allowed_domains
            )
            if not allowed:
                return False

        # Исключённые паттерны
        for pattern in self._exclude_patterns:
            if pattern.search(url):
                return False

        # Включающие паттерны (если указаны)
        if self._url_patterns:
            matched = any(p.search(url) for p in self._url_patterns)
            if not matched:
                return False

        return True

    def normalize(self, url: str) -> str:
        """Нормализовать URL."""
        # Убрать фрагмент
        parsed = urlparse(url)
        normalized = parsed._replace(fragment="").geturl()
        # Убрать trailing slash
        if normalized.endswith("/") and len(normalized) > len(parsed.scheme) + 3:
            normalized = normalized.rstrip("/")
        return normalized


# ═══════════════════════════════════════════════════════════════════════════════
# 9. CrawlerEngine — главный оркестратор
# ═══════════════════════════════════════════════════════════════════════════════

class CrawlerEngine:
    """Главный движок краулера — оркестрирует все компоненты."""

    def __init__(self, config: CrawlerConfig):
        self.config = config

        # Компоненты
        self.proxy_manager = ProxyManager(config)
        self.rate_limiter = RateLimiter(config)
        self.robots_handler = RobotsHandler(
            respect_robots=config.respect_robots_txt,
            parse_sitemap=config.parse_sitemap,
        )
        self.url_filter = URLFilter(config)
        self.content_extractor = ContentExtractor(config)
        self.result_store = ResultStore(config)

        # Состояние
        self._visited_urls: set[str] = set()
        self._content_hashes: set[str] = set()
        self._domain_counts: dict[str, int] = {}
        self._pages_crawled = 0
        self._pages_failed = 0
        self._start_time = 0.0

        # Настройка логирования
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Настроить логирование."""
        logger.remove()
        level = "DEBUG" if self.config.verbose else "INFO"
        logger.add(sys.stderr, level=level, format="<level>{level: <8}</level> | <cyan>{message}</cyan>")
        if self.config.log_file:
            logger.add(self.config.log_file, level="DEBUG", rotation="10 MB")

    async def crawl(self) -> dict[str, Any]:
        """Запустить краулинг.

        Returns:
            Статистика краулинга
        """
        self._start_time = time.time()

        logger.info("=" * 60)
        logger.info("🕷️  Distributed Crawler Framework v2.0")
        logger.info("=" * 60)
        logger.info(f"Seeds: {self.config.seeds}")
        logger.info(f"Max depth: {self.config.max_depth}, Max pages: {self.config.max_pages}")
        logger.info(f"Stealth: {self.config.stealth_level} (enabled={self.config.stealth_enabled})")
        logger.info(f"Proxy: {self.config.proxy_enabled}")
        logger.info(f"Workers: {self.config.workers}")
        logger.info(f"Output: {self.config.output_format} → {self.config.output_directory}")
        logger.info("=" * 60)

        # Загрузить прокси
        if self.config.proxy_enabled:
            self.proxy_manager.load()

        # Инициализировать браузер
        fetcher = PageFetcher(self.config, self.proxy_manager)
        await fetcher.start()

        try:
            # Загрузить sitemap для каждого сида
            if self.config.parse_sitemap:
                await self._load_sitemaps()

            # Запустить BFS краулинг
            await self._crawl_bfs(fetcher)

        finally:
            await fetcher.stop()

        # Сохранить результаты
        elapsed = time.time() - self._start_time
        stats = self._build_stats(elapsed)

        if self.config.output_format in ("json", "both"):
            self.result_store.save_json()
        self.result_store.save_stats(stats)
        self.result_store.close()

        self._print_summary(stats)
        return stats

    async def _load_sitemaps(self) -> None:
        """Загрузить sitemap.xml для сидов."""
        for seed in self.config.seeds:
            parsed = urlparse(seed)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            urls = await self.robots_handler.get_sitemap_urls(domain)
            if urls:
                logger.info(f"Sitemap for {domain}: {len(urls)} URLs")
                # Добавить URL из sitemap как сиды глубины 0
                for url in urls[:self.config.max_pages]:
                    normalized = self.url_filter.normalize(url)
                    if normalized not in self._visited_urls:
                        self._visited_urls.add(normalized)

    async def _crawl_bfs(self, fetcher: PageFetcher) -> None:
        """BFS краулинг с очередью."""
        # Очередь: (url, depth)
        queue: list[tuple[str, int]] = []
        for seed in self.config.seeds:
            normalized = self.url_filter.normalize(seed)
            queue.append((normalized, 0))
            self._visited_urls.add(normalized)

        while queue and self._pages_crawled < self.config.max_pages:
            # Батч для параллельной обработки
            batch: list[tuple[str, int]] = []
            while queue and len(batch) < self.config.workers:
                batch.append(queue.pop(0))

            if not batch:
                break

            # Параллельная загрузка батча
            tasks = [
                self._crawl_page(fetcher, url, depth)
                for url, depth in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Обработать результаты
            for i, result in enumerate(results):
                url, depth = batch[i]

                if isinstance(result, Exception):
                    logger.error(f"Crawl error for {url}: {result}")
                    self._pages_failed += 1
                    continue

                if result is None:
                    self._pages_failed += 1
                    continue

                self._pages_crawled += 1

                # Добавить новые URL в очередь
                if depth < self.config.max_depth:
                    new_links = self.content_extractor.extract_links(result)
                    for link in new_links:
                        absolute_url = urljoin(url, link)
                        normalized = self.url_filter.normalize(absolute_url)

                        if normalized not in self._visited_urls and self.url_filter.should_crawl(normalized, depth + 1):
                            self._visited_urls.add(normalized)
                            queue.append((normalized, depth + 1))

                # Прогресс
                if self._pages_crawled % 10 == 0:
                    logger.info(f"Progress: {self._pages_crawled}/{self.config.max_pages} pages crawled")

    async def _crawl_page(
        self,
        fetcher: PageFetcher,
        url: str,
        depth: int,
    ) -> dict[str, Any] | None:
        """Краулить одну страницу."""
        domain = urlparse(url).netloc

        # Проверить лимит на домен
        if self.config.max_pages_per_domain > 0:
            domain_count = self._domain_counts.get(domain, 0)
            if domain_count >= self.config.max_pages_per_domain:
                logger.debug(f"Domain limit reached for {domain}")
                return None

        # Rate limiting
        await self.rate_limiter.acquire(domain)

        # robots.txt
        if not await self.robots_handler.can_fetch(url):
            logger.debug(f"Blocked by robots.txt: {url}")
            return None

        # Загрузить страницу
        page, fetch_metadata = await fetcher.fetch(url)

        if page is None:
            logger.warning(f"Failed to fetch: {url} — {fetch_metadata.get('error', 'unknown')}")
            return None

        try:
            # Извлечь данные
            result = await self.content_extractor.extract(page, url, depth)

            # Дедупликация контента
            if self.config.dedup_content and result.get("content_hash"):
                if result["content_hash"] in self._content_hashes:
                    logger.debug(f"Duplicate content: {url}")
                    return None
                self._content_hashes.add(result["content_hash"])

            # Скриншот
            if self.config.save_screenshots:
                try:
                    screenshot_path = await fetcher.take_screenshot(page, url, self.result_store.output_dir)
                    result["screenshot_path"] = screenshot_path
                except Exception as e:
                    logger.debug(f"Screenshot error: {e}")

            # HTML
            if self.config.save_html:
                try:
                    html_path = await fetcher.save_html(page, url, self.result_store.output_dir)
                    result["html_path"] = html_path
                except Exception as e:
                    logger.debug(f"HTML save error: {e}")

            # Обновить счётчики
            self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1

            # Случайная задержка
            await self.rate_limiter.delay()

            # Сохранить результат
            self.result_store.add_result(result)

            logger.info(f"✅ [{depth}] {url} — {result.get('title', '')[:60]} ({result.get('text_length', 0)} chars)")
            return result

        finally:
            try:
                await page.close()
            except Exception:
                pass

    def _build_stats(self, elapsed: float) -> dict[str, Any]:
        """Построить статистику краулинга."""
        return {
            "elapsed_seconds": round(elapsed, 2),
            "pages_crawled": self._pages_crawled,
            "pages_failed": self._pages_failed,
            "total_urls_discovered": len(self._visited_urls),
            "unique_domains": len(self._domain_counts),
            "domain_counts": self._domain_counts,
            "pages_per_second": round(self._pages_crawled / max(elapsed, 0.01), 2),
            "proxy_stats": self.proxy_manager.stats,
            "config": {
                "max_depth": self.config.max_depth,
                "max_pages": self.config.max_pages,
                "stealth_level": self.config.stealth_level,
                "proxy_enabled": self.config.proxy_enabled,
            },
        }

    def _print_summary(self, stats: dict[str, Any]) -> None:
        """Вывести сводку краулинга."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 CRAWL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  Pages crawled:    {stats['pages_crawled']}")
        logger.info(f"  Pages failed:     {stats['pages_failed']}")
        logger.info(f"  URLs discovered:  {stats['total_urls_discovered']}")
        logger.info(f"  Unique domains:   {stats['unique_domains']}")
        logger.info(f"  Elapsed time:     {stats['elapsed_seconds']}s")
        logger.info(f"  Speed:            {stats['pages_per_second']} pages/s")
        logger.info(f"  Output:           {self.config.output_directory}")
        logger.info("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. CLI
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """Построить парсер CLI-аргументов."""
    parser = argparse.ArgumentParser(
        prog="distributed_crawler",
        description="🕷️ Distributed Crawler Framework для Lab Playwright Kit v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Простой запуск с одним сидом
  PYTHONPATH=src python3 scripts/distributed_crawler.py --seed https://example.com --depth 1

  # Полный краулинг с конфигом
  PYTHONPATH=src python3 scripts/distributed_crawler.py --config config.yaml

  # Краулинг со стелсом и скриншотами
  PYTHONPATH=src python3 scripts/distributed_crawler.py --seed https://example.com --stealth --output ./output
        """,
    )

    # Источник
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--config", "-c",
        type=str,
        help="YAML конфигурационный файл",
    )
    source.add_argument(
        "--seed", "-s",
        type=str,
        help="Seed URL (простой режим)",
    )

    # Параметры краулинга
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=None,
        help="Максимальная глубина краулинга (по умолчанию: 2)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Максимальное количество страниц (по умолчанию: 50)",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Количество параллельных воркеров (по умолчанию: 3)",
    )

    # Выход
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Директория для выходных данных (по умолчанию: ./crawl_output)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "sqlite", "both"],
        default=None,
        help="Формат выходных данных (по умолчанию: json)",
    )

    # Stealth
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Включить stealth-режим",
    )
    parser.add_argument(
        "--stealth-level",
        choices=["minimal", "standard", "advanced", "full"],
        default=None,
        help="Уровень stealth-маскировки (по умолчанию: standard)",
    )

    # Прокси
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Файл с прокси (включает proxy)",
    )

    # Браузер
    parser.add_argument(
        "--headless",
        type=bool,
        default=None,
        help="Headless режим браузера (по умолчанию: True)",
    )

    # Дополнительно
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Сохранять скриншоты страниц",
    )
    parser.add_argument(
        "--save-html",
        action="store_true",
        help="Сохранять HTML страниц",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробное логирование",
    )

    return parser


async def main_async() -> dict[str, Any]:
    """Асинхронная точка входа."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.config and not args.seed:
        parser.print_help()
        logger.error("Необходимо указать --config или --seed")
        sys.exit(1)

    # Загрузить конфигурацию
    config = CrawlerConfig.from_args(args)

    # CLI-специфичные переопределения
    if args.format:
        config.output_format = args.format
    if args.screenshots:
        config.save_screenshots = True
    if args.save_html:
        config.save_html = True
    if args.stealth_level:
        config.stealth_level = args.stealth_level

    # Запустить краулер
    engine = CrawlerEngine(config)
    stats = await engine.crawl()

    return stats


def main() -> None:
    """Точка входа для CLI."""
    try:
        stats = asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info('Crawler interrupted by user')
        sys.exit(130)
    except Exception as e:
        logger.critical(f'Crawler fatal error: {e}')
        sys.exit(2)

    # Exit code на основе результатов
    if stats["pages_crawled"] == 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
