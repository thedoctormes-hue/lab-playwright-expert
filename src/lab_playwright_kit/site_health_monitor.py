"""
Site Health Monitor — мониторинг здоровья сайтов лаборатории.

Проверяет: HTTP статус, время загрузки, SSL сертификат, ключевые слова.
Интеграция с Telegram для алертов.

Использование:
    >>> from lab_playwright_kit.site_health_monitor import SiteHealthMonitor, SiteConfig
    >>> monitor = SiteHealthMonitor()
    >>> monitor.add_site(SiteConfig(url="https://snablab.shtab-ai.ru", name="СнабЛаб"))
    >>> results = await monitor.check_all()
    >>> await monitor.report_to_telegram(results, bot_token, chat_id)
"""
from __future__ import annotations

import asyncio
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp
import certifi
from loguru import logger


@dataclass
class SiteConfig:
    """Конфигурация сайта для мониторинга."""
    url: str
    name: str
    expected_status: int = 200
    expected_keywords: list[str] = field(default_factory=list)
    timeout: float = 15.0
    max_load_time: float = 5.0  # секунд
    check_ssl: bool = True
    ssl_expiry_warning_days: int = 14


@dataclass
class SiteCheckResult:
    """Результат проверки одного сайта."""
    url: str
    name: str
    timestamp: str
    status: str = "unknown"  # ok, degraded, down, error
    http_status: int = 0
    load_time: float = 0.0
    ssl_valid: bool = True
    ssl_expiry_days: int = -1
    keywords_found: list[str] = field(default_factory=list)
    keywords_missing: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def is_healthy(self) -> bool:
        return self.status == "ok"

    @property
    def is_down(self) -> bool:
        return self.status in ("down", "error")

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "name": self.name,
            "status": self.status,
            "http_status": self.http_status,
            "load_time": round(self.load_time, 2),
            "ssl_valid": self.ssl_valid,
            "ssl_expiry_days": self.ssl_expiry_days,
            "keywords_found": self.keywords_found,
            "keywords_missing": self.keywords_missing,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class HealthReport:
    """Полный отчёт о здоровье всех сайтов."""
    results: list[SiteCheckResult] = field(default_factory=list)
    total_sites: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    down_count: int = 0
    check_duration: float = 0.0
    timestamp: str = ""

    @property
    def all_healthy(self) -> bool:
        return self.down_count == 0 and self.degraded_count == 0

    @property
    def has_issues(self) -> bool:
        return self.down_count > 0 or self.degraded_count > 0

    def to_dict(self) -> dict:
        return {
            "total_sites": self.total_sites,
            "healthy": self.healthy_count,
            "degraded": self.degraded_count,
            "down": self.down_count,
            "all_healthy": self.all_healthy,
            "check_duration": round(self.check_duration, 2),
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
        }

    def to_telegram_message(self) -> str:
        """Форматировать отчёт для Telegram."""
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        lines = [f"🏥 Здоровье сайтов — {now}", ""]

        for r in self.results:
            if r.status == "ok":
                icon = "✅"
            elif r.status == "degraded":
                icon = "⚠️"
            else:
                icon = "❌"

            lines.append(f"{icon} {r.name}")
            lines.append(f"   URL: {r.url}")
            lines.append(f"   HTTP: {r.http_status} | Загрузка: {r.load_time:.1f}с")

            if not r.ssl_valid:
                lines.append(f"   🔒 SSL: НЕВАЛИДЕН")
            elif r.ssl_expiry_days >= 0 and r.ssl_expiry_days <= 14:
                lines.append(f"   🔒 SSL: истекает через {r.ssl_expiry_days} дней")

            if r.keywords_missing:
                lines.append(f"   🔍 Не найдены: {', '.join(r.keywords_missing)}")

            if r.error:
                lines.append(f"   ❗ Ошибка: {r.error}")

            lines.append("")

        lines.append(f"Итого: {self.healthy_count}✅ {self.degraded_count}⚠️ {self.down_count}❌")
        lines.append(f"Проверка заняла: {self.check_duration:.1f}с")

        return "\n".join(lines)


class SiteHealthMonitor:
    """Мониторинг здоровья сайтов лаборатории.

    Проверяет:
    - HTTP статус (200, 301, 302 и т.д.)
    - Время загрузки
    - SSL сертификат (валидность, срок истечения)
    - Наличие ключевых слов на странице

    Использование:
        monitor = SiteHealthMonitor()
        monitor.add_site(SiteConfig(url="https://snablab.shtab-ai.ru", name="СнабЛаб",
                                     expected_keywords=["СнабЛаб", "Войти"]))
        results = await monitor.check_all()
    """

    def __init__(self, max_concurrency: int = 5):
        self._sites: list[SiteConfig] = []
        self._max_concurrency = max_concurrency
        self._history: list[HealthReport] = []

    def add_site(self, site: SiteConfig) -> None:
        """Добавить сайт для мониторинга."""
        self._sites.append(site)
        logger.info(f"Added site for monitoring: {site.name} ({site.url})")

    def remove_site(self, url: str) -> None:
        """Удалить сайт из мониторинга."""
        self._sites = [s for s in self._sites if s.url != url]

    @property
    def sites(self) -> list[SiteConfig]:
        return list(self._sites)

    async def check_site(self, site: SiteConfig) -> SiteCheckResult:
        """Проверить один сайт."""
        result = SiteCheckResult(
            url=site.url,
            name=site.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        start = time.time()

        try:
            timeout = aiohttp.ClientTimeout(total=site.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(site.url, allow_redirects=True, ssl=certifi.where()) as resp:
                    result.http_status = resp.status
                    result.load_time = time.time() - start

                    body = await resp.text()

                    # Проверка ключевых слов
                    for keyword in site.expected_keywords:
                        if keyword.lower() in body.lower():
                            result.keywords_found.append(keyword)
                        else:
                            result.keywords_missing.append(keyword)

        except aiohttp.ClientError as e:
            result.status = "down"
            result.error = str(e)
            result.load_time = time.time() - start
            logger.warning(f"Site check failed [{site.name}]: {e}")
            return result
        except asyncio.TimeoutError:
            result.status = "down"
            result.error = f"Timeout after {site.timeout}s"
            result.load_time = time.time() - start
            logger.warning(f"Site check timeout [{site.name}]")
            return result
        except Exception as e:
            result.status = "error"
            result.error = str(e)
            result.load_time = time.time() - start
            logger.error(f"Site check error [{site.name}]: {e}")
            return result

        # SSL проверка
        if site.check_ssl and site.url.startswith("https://"):
            ssl_info = self._check_ssl(site.url)
            result.ssl_valid = ssl_info.get("valid", True)
            result.ssl_expiry_days = ssl_info.get("expiry_days", -1)

        # Определение статуса
        if result.http_status != site.expected_status:
            result.status = "down"
        elif result.load_time > site.max_load_time:
            result.status = "degraded"
        elif result.keywords_missing:
            result.status = "degraded"
        elif not result.ssl_valid:
            result.status = "degraded"
        elif result.ssl_expiry_days >= 0 and result.ssl_expiry_days <= site.ssl_expiry_warning_days:
            result.status = "degraded"
        else:
            result.status = "ok"

        return result

    async def check_all(self) -> HealthReport:
        """Проверить все сайты."""
        start = time.time()
        now = datetime.now(timezone.utc).isoformat()

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _check_with_limit(site: SiteConfig) -> SiteCheckResult:
            async with semaphore:
                return await self.check_site(site)

        tasks = [_check_with_limit(site) for site in self._sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обработка результатов
        processed_results: list[SiteCheckResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Если сама проверка упала — создаём error result
                processed_results.append(SiteCheckResult(
                    url=self._sites[i].url,
                    name=self._sites[i].name,
                    timestamp=now,
                    status="error",
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        # Подсчёт статистики
        healthy = sum(1 for r in processed_results if r.status == "ok")
        degraded = sum(1 for r in processed_results if r.status == "degraded")
        down = sum(1 for r in processed_results if r.status in ("down", "error"))

        report = HealthReport(
            results=processed_results,
            total_sites=len(processed_results),
            healthy_count=healthy,
            degraded_count=degraded,
            down_count=down,
            check_duration=time.time() - start,
            timestamp=now,
        )

        self._history.append(report)

        logger.info(
            f"Site health check: {healthy} ok, {degraded} degraded, {down} down "
            f"({report.check_duration:.1f}s)"
        )

        return report

    async def report_to_telegram(
        self,
        report: HealthReport,
        bot_token: str,
        chat_id: str,
    ) -> bool:
        """Отправить отчёт в Telegram."""
        if not report.has_issues:
            logger.info("All sites healthy, skipping Telegram report")
            return True

        message = report.to_telegram_message()

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }) as resp:
                    if resp.status == 200:
                        logger.info(f"Telegram alert sent to {chat_id}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"Telegram API error: {resp.status} {body}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

    def _check_ssl(self, url: str) -> dict:
        """Проверить SSL сертификат сайта."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return {"valid": False, "expiry_days": -1}

            context = ssl.create_default_context(cafile=certifi.where())
            with socket.create_connection((hostname, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    expiry = cert.get("notAfter", "")
                    if expiry:
                        from datetime import datetime as dt
                        expiry_date = dt.strptime(expiry, "%b %d %H:%M:%S %Y %Z")
                        days_left = (expiry_date - dt.utcnow()).days
                        return {"valid": True, "expiry_days": days_left}
                    return {"valid": True, "expiry_days": -1}
        except Exception as e:
            logger.warning(f"SSL check failed for {url}: {e}")
            return {"valid": False, "expiry_days": -1}

    def get_history(self, limit: int = 10) -> list[HealthReport]:
        """Получить историю проверок."""
        return self._history[-limit:]

    @staticmethod
    def default_laboratory_sites() -> list[SiteConfig]:
        """Предустановленные сайты лаборатории."""
        return [
            SiteConfig(
                url="https://snablab.shtab-ai.ru",
                name="СнабЛаб",
                expected_keywords=["СнабЛаб"],
                max_load_time=3.0,
            ),
            SiteConfig(
                url="https://articles.shtab-ai.ru",
                name="Блог (articles)",
                expected_keywords=["DoctorM&Ai", "статьи"],
                max_load_time=5.0,
            ),
        ]


# ─── CLI ──────────────────────────────────────────────────────────────────────

async def run_check(
    bot_token: str = "",
    chat_id: str = "",
    sites: list[SiteConfig] | None = None,
) -> HealthReport:
    """Запустить проверку и отправить отчёт.

    Удобная функция для запуска из CLI или cron.

    Пример:
        report = await run_check(bot_token="xxx", chat_id="-1003588235089")
    """
    monitor = SiteHealthMonitor()

    if sites is None:
        sites = SiteHealthMonitor.default_laboratory_sites()

    for site in sites:
        monitor.add_site(site)

    report = await monitor.check_all()

    if bot_token and chat_id and report.has_issues:
        await monitor.report_to_telegram(report, bot_token, chat_id)

    return report


if __name__ == "__main__":
    import sys
    import json as json_mod

    async def main():
        report = await run_check()
        print(json_mod.dumps(report.to_dict(), indent=2, ensure_ascii=False))

        if report.has_issues:
            sys.exit(1)

    asyncio.run(main())
