"""
VPN Monitor — мониторинг VPN-серверов через браузер.

Проверяет:
- Доступность VPN-туннеля (IP меняется)
- Доступность сайтов через VPN
- Скорость загрузки
- Алерт в Telegram при проблемах

Использование:
    >>> from lab_playwright_kit.vpn_monitor import VPNMonitor, VPNServer
    >>> monitor = VPNMonitor()
    >>> monitor.add_server(VPNServer(name="poland", proxy_url="socks5://127.0.0.1:10808", country="PL"))
    >>> report = await monitor.check_all()
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp
import certifi
from loguru import logger

from .vpn_proxy import VPNProxy, VPNProxyManager

# ─── Конфигурация ─────────────────────────────────────────────────────────────

DEFAULT_TEST_SITES = [
    "https://google.com",
    "https://youtube.com",
    "https://github.com",
    "https://wikipedia.org",
    "https://stackoverflow.com",
    "https://reddit.com",
    "https://twitter.com",
    "https://amazon.com",
    "https://yahoo.com",
    "https://bing.com",
]

IP_CHECK_URL = "https://api.ipify.org?format=json"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_LOAD_TIME = 10.0


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class VPNServer:
    """Конфигурация VPN-сервера для мониторинга."""
    name: str
    proxy_url: str | None  # socks5://127.0.0.1:10808 или None для direct
    country: str = ""
    expected_ip: str = ""
    description: str = ""
    timeout: float = DEFAULT_TIMEOUT
    max_load_time: float = DEFAULT_MAX_LOAD_TIME
    test_sites: list[str] = field(default_factory=lambda: DEFAULT_TEST_SITES[:5])

    @property
    def is_direct(self) -> bool:
        return self.proxy_url is None


@dataclass
class SiteCheck:
    """Результат проверки одного сайта через VPN."""
    url: str
    status: str  # "ok", "slow", "down", "error"
    http_status: int = 0
    load_time: float = 0.0
    error: str = ""


@dataclass
class VPNCheckResult:
    """Результат проверки VPN-сервера."""
    server_name: str
    country: str
    timestamp: str
    status: str  # "ok", "degraded", "down", "error"
    exit_ip: str = ""
    expected_ip: str = ""
    ip_match: bool = True
    sites: list[SiteCheck] = field(default_factory=list)
    avg_load_time: float = 0.0
    error: str = ""
    check_duration: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.status == "ok"

    @property
    def is_down(self) -> bool:
        return self.status in ("down", "error")

    @property
    def sites_ok(self) -> int:
        return sum(1 for s in self.sites if s.status == "ok")

    @property
    def sites_total(self) -> int:
        return len(self.sites)

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "country": self.country,
            "status": self.status,
            "exit_ip": self.exit_ip,
            "ip_match": self.ip_match,
            "sites_ok": self.sites_ok,
            "sites_total": self.sites_total,
            "avg_load_time": round(self.avg_load_time, 3),
            "error": self.error,
        }


@dataclass
class VPNMonitorReport:
    """Полный отчёт мониторинга VPN."""
    results: list[VPNCheckResult]
    total_servers: int
    healthy_count: int
    degraded_count: int
    down_count: int
    check_duration: float
    timestamp: str = ""

    @property
    def all_healthy(self) -> bool:
        return self.healthy_count == self.total_servers

    @property
    def has_issues(self) -> bool:
        return self.down_count > 0 or self.degraded_count > 0

    def to_telegram_message(self) -> str:
        lines = ["🔍 <b>VPN Monitor Report</b>\n"]

        for r in self.results:
            if r.status == "ok":
                icon = "✅"
            elif r.status == "degraded":
                icon = "⚠️"
            else:
                icon = "❌"

            lines.append(f"{icon} <b>{r.server_name}</b> ({r.country})")
            lines.append(f"   IP: {r.exit_ip or 'N/A'} {'✓' if r.ip_match else '✗'}")
            lines.append(f"   Sites: {r.sites_ok}/{r.sites_total} ok")
            lines.append(f"   Avg: {r.avg_load_time:.2f}s")
            if r.error:
                lines.append(f"   Error: {r.error}")
            lines.append("")

        lines.append(f"⏱ Duration: {self.check_duration:.1f}s")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_servers": self.total_servers,
            "healthy_count": self.healthy_count,
            "degraded_count": self.degraded_count,
            "down_count": self.down_count,
            "all_healthy": self.all_healthy,
            "check_duration": round(self.check_duration, 2),
            "results": [r.to_dict() for r in self.results],
        }


# ─── Monitor ──────────────────────────────────────────────────────────────────

class VPNMonitor:
    """Мониторинг VPN-серверов."""

    def __init__(self):
        self._servers: list[VPNServer] = []
        self._history: list[VPNMonitorReport] = []

    def add_server(self, server: VPNServer) -> None:
        self._servers.append(server)
        logger.info(f"VPN monitor: added server '{server.name}' ({server.country})")

    def remove_server(self, name: str) -> None:
        self._servers = [s for s in self._servers if s.name != name]

    @property
    def servers(self) -> list[VPNServer]:
        return list(self._servers)

    @staticmethod
    def from_vpn_manager(manager: VPNProxyManager) -> VPNMonitor:
        """Создать монитор из VPNProxyManager."""
        monitor = VPNMonitor()
        for proxy in manager.proxies:
            monitor.add_server(VPNServer(
                name=proxy.name,
                proxy_url=proxy.server,
                country=proxy.country,
                expected_ip=proxy.exit_ip,
                description=proxy.description,
            ))
        return monitor

    async def check_server(self, server: VPNServer) -> VPNCheckResult:
        """Проверить один VPN-сервер."""
        start = time.time()
        result = VPNCheckResult(
            server_name=server.name,
            country=server.country,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="ok",
            expected_ip=server.expected_ip,
        )

        try:
            # Определяем прокси
            proxy = server.proxy_url if not server.is_direct else None

            timeout = aiohttp.ClientTimeout(total=server.timeout)

            # Проверяем IP
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    kwargs: dict[str, Any] = {}
                    if proxy:
                        kwargs["proxy"] = proxy
                    else:
                        kwargs["ssl"] = certifi.where()

                    async with session.get(IP_CHECK_URL, **kwargs) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result.exit_ip = data.get("ip", "")
                            if server.expected_ip and result.exit_ip != server.expected_ip:
                                result.ip_match = False
                                logger.warning(
                                    f"VPN [{server.name}] IP mismatch: "
                                    f"expected {server.expected_ip}, got {result.exit_ip}"
                                )
                        else:
                            result.ip_match = False
                except Exception as e:
                    result.ip_match = False
                    result.error = f"IP check failed: {e}"
                    logger.warning(f"VPN [{server.name}] IP check failed: {e}")

            # Проверяем сайты
            async with aiohttp.ClientSession(timeout=timeout) as session:
                site_tasks = [self._check_site(session, url, server) for url in server.test_sites]
                result.sites = await asyncio.gather(*site_tasks, return_exceptions=False)

            # Считаем среднюю скорость
            load_times = [s.load_time for s in result.sites if s.status == "ok"]
            if load_times:
                result.avg_load_time = sum(load_times) / len(load_times)

            # Определяем статус
            ok_count = sum(1 for s in result.sites if s.status == "ok")
            total = len(result.sites)

            if ok_count == 0 and total > 0:
                result.status = "down"
            elif ok_count < total or not result.ip_match or result.avg_load_time > server.max_load_time:
                result.status = "degraded"

        except Exception as e:
            result.status = "error"
            result.error = str(e)
            logger.error(f"VPN [{server.name}] check error: {e}")

        result.check_duration = time.time() - start
        return result

    async def _check_site(
        self, session: aiohttp.ClientSession, url: str, server: VPNServer
    ) -> SiteCheck:
        """Проверить один сайт через VPN."""
        check = SiteCheck(url=url, status="ok")
        start = time.time()

        try:
            kwargs: dict[str, Any] = {"allow_redirects": True}
            if server.proxy_url:
                kwargs["proxy"] = server.proxy_url
            else:
                kwargs["ssl"] = certifi.where()

            async with session.get(url, **kwargs) as resp:
                check.http_status = resp.status
                check.load_time = time.time() - start

                if resp.status >= 400:
                    check.status = "down"
                    check.error = f"HTTP {resp.status}"
                elif check.load_time > server.max_load_time:
                    check.status = "slow"

        except aiohttp.ClientError as e:
            check.status = "down"
            check.error = str(e)
            check.load_time = time.time() - start
        except asyncio.TimeoutError:
            check.status = "down"
            check.error = f"Timeout after {server.timeout}s"
            check.load_time = time.time() - start
        except Exception as e:
            check.status = "error"
            check.error = str(e)
            check.load_time = time.time() - start

        return check

    async def check_all(self) -> VPNMonitorReport:
        """Проверить все VPN-серверы."""
        start = time.time()
        logger.info(f"VPN monitor: checking {len(self._servers)} servers...")

        tasks = [self.check_server(s) for s in self._servers]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        healthy = sum(1 for r in results if r.status == "ok")
        degraded = sum(1 for r in results if r.status == "degraded")
        down = sum(1 for r in results if r.status in ("down", "error"))

        report = VPNMonitorReport(
            results=list(results),
            total_servers=len(results),
            healthy_count=healthy,
            degraded_count=degraded,
            down_count=down,
            check_duration=time.time() - start,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._history.append(report)
        logger.info(
            f"VPN monitor: {healthy} ok, {degraded} degraded, {down} down "
            f"({report.check_duration:.1f}s)"
        )
        return report

    async def report_to_telegram(
        self, report: VPNMonitorReport, bot_token: str, chat_id: str
    ) -> bool:
        """Отправить отчёт в Telegram."""
        if not report.has_issues:
            logger.info("VPN monitor: all servers healthy, skipping Telegram report")
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
                        logger.info(f"VPN monitor: Telegram alert sent to {chat_id}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"VPN monitor: Telegram API error: {resp.status} {body}")
                        return False
        except Exception as e:
            logger.error(f"VPN monitor: failed to send Telegram alert: {e}")
            return False

    def get_history(self) -> list[VPNMonitorReport]:
        return list(self._history)

    @staticmethod
    def default_laboratory_servers() -> list[VPNServer]:
        """Серверы лаборатории по умолчанию."""
        return [
            VPNServer(
                name="poland",
                proxy_url="socks5://127.0.0.1:10808",
                country="PL",
                expected_ip="78.17.43.205",
                description="Poland VPN server",
            ),
            VPNServer(
                name="florida",
                proxy_url="socks5://127.0.0.1:10809",
                country="US",
                expected_ip="",
                description="Florida VPN server",
            ),
            VPNServer(
                name="direct",
                proxy_url=None,
                country="DIRECT",
                expected_ip="",
                description="Direct connection (no VPN)",
            ),
        ]


async def run_check(
    servers: list[VPNServer] | None = None,
    telegram_token: str = "",
    telegram_chat: str = "",
) -> VPNMonitorReport:
    """Быстрый запуск проверки VPN."""
    monitor = VPNMonitor()

    if servers:
        for s in servers:
            monitor.add_server(s)
    else:
        for s in VPNMonitor.default_laboratory_servers():
            monitor.add_server(s)

    report = await monitor.check_all()

    if telegram_token and telegram_chat and report.has_issues:
        await monitor.report_to_telegram(report, telegram_token, telegram_chat)

    return report
