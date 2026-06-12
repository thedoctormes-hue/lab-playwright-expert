"""
Health Monitor модуль для Lab Playwright Kit.

Мониторинг работоспособности ботов и скриптов.
Интеграция с Healthchecks.io и Telegram-алертами.

Использование:
    >>> from lab_playwright_kit.health_monitor import HealthMonitor, HealthCheck
    >>> monitor = HealthMonitor(healthchecks_url="https://hc-ping.com/uuid")
    >>> await monitor.ping(status="ok")
    >>> await monitor.check_and_alert(check_func=my_bot_health)
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import httpx
from loguru import logger


# ─── Data classes ─────────────────────────────────────────────────────────────

class HealthStatus(str, Enum):
    """Статус здоровья компонента."""
    OK = "ok"
    DEGRADED = "degraded"
    FAILING = "failing"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Результат одной проверки здоровья.

    Attributes:
        name: Имя проверки (например, "vpn-bot", "playwright-parser")
        status: Статус здоровья
        message: Описание состояния
        latency_ms: Время ответа в мс
        metadata: Дополнительные данные
        timestamp: Время проверки
        error: Текст ошибки (если есть)
    """

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    error: str | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "error": self.error,
        }

    def __str__(self) -> str:
        icons = {
            HealthStatus.OK: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.FAILING: "🔴",
            HealthStatus.DOWN: "❌",
            HealthStatus.UNKNOWN: "❓",
        }
        icon = icons.get(self.status, "❓")
        return f"{icon} [{self.name}] {self.status.value}: {self.message} ({self.latency_ms:.0f}ms)"


@dataclass
class HealthReport:
    """Отчёт о здоровье всех компонентов.

    Attributes:
        checks: Список проверок
        overall_status: Общий статус
        uptime_percent: Процент аптайма
    """

    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def overall_status(self) -> HealthStatus:
        if not self.checks:
            return HealthStatus.UNKNOWN
        statuses = [c.status for c in self.checks]
        if any(s == HealthStatus.DOWN for s in statuses):
            return HealthStatus.DOWN
        if any(s == HealthStatus.FAILING for s in statuses):
            return HealthStatus.FAILING
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        if all(s == HealthStatus.OK for s in statuses):
            return HealthStatus.OK
        return HealthStatus.UNKNOWN

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.checks if c.is_healthy)

    @property
    def total_count(self) -> int:
        return len(self.checks)

    @property
    def uptime_percent(self) -> float:
        if not self.checks:
            return 0.0
        return (self.healthy_count / self.total_count) * 100

    def summary(self) -> str:
        lines = [
            "═══ Health Report ═══",
            f"Overall: {self.overall_status.value.upper()} | "
            f"Healthy: {self.healthy_count}/{self.total_count} ({self.uptime_percent:.0f}%)",
            "",
        ]
        for check in self.checks:
            lines.append(f"  {check}")
        return "\n".join(lines)


# ─── Health Monitor ──────────────────────────────────────────────────────────

class HealthMonitor:
    """Мониторинг здоровья с интеграцией Healthchecks.io и Telegram.

    Использование:
        >>> monitor = HealthMonitor(
        ...     healthchecks_url="https://hc-ping.com/your-uuid",
        ...     telegram_token="...",
        ...     telegram_chat_id="...",
        ... )
        >>> # Одноразовый ping
        >>> await monitor.ping("my-bot", status="ok")
        """
    
    def __init__(
        self,
        healthchecks_url: str | None = None,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
        timeout: float = 10.0,
    ):
        self._hc_url = healthchecks_url
        self._tg_token = telegram_token
        self._tg_chat_id = telegram_chat_id
        self._timeout = timeout
        self._check_history: dict[str, list[HealthCheck]] = {}

    async def ping(
        self,
        name: str = "default",
        status: str = "ok",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> HealthCheck:
        """Отправить ping в Healthchecks.io.

        Args:
            name: Имя проверки
            status: ok, fail, или числовой код
            message: Сообщение
            metadata: Дополнительные данные

        Returns:
            HealthCheck с результатом
        """
        check = HealthCheck(
            name=name,
            status=HealthStatus.OK if status == "ok" else HealthStatus.FAILING,
            message=message,
            metadata=metadata or {},
        )

        if self._hc_url:
            try:
                # Healthchecks.io поддерживает /uuid/slug для разных проверок
                url = self._hc_url
                if name != "default":
                    base = self._rstrip(self._hc_url, "/")
                    url = f"{base}/{name}"

                payload = {
                    "status": status,
                    "msg": message,
                    "metadata": metadata or {},
                }

                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    if status == "ok":
                        response = await client.get(url)
                    else:
                        # Для fail/start/log — POST с данными
                        response = await client.post(url, data=payload)

                check.latency_ms = response.elapsed.total_seconds() * 1000
                check.message = f"HC ping OK (HTTP {response.status_code})"
                logger.debug(f"HealthMonitor ping: {name} → {status} ({check.latency_ms:.0f}ms)")

            except Exception as e:
                check.error = str(e)
                check.status = HealthStatus.DEGRADED
                logger.warning(f"HealthMonitor ping failed for {name}: {e}")
        else:
            check.message = "No healthchecks URL configured"
            logger.debug(f"HealthMonitor: no HC URL, skipping ping for {name}")

        self._record_check(check)
        return check

    async def check_and_alert(
        self,
        name: str,
        check_func: Callable[..., Coroutine[Any, Any, bool]],
        alert_on_failure: bool = True,
        **kwargs: Any,
    ) -> HealthCheck:
        """Выполнить функцию проверки и отправить результат.

        Args:
            name: Имя проверки
            check_func: Асинхронная функция, возвращающая True если OK
            alert_on_failure: Отправлять алерт при провале
            **kwargs: Аргументы для check_func

        Returns:
            HealthCheck с результатом
        """
        start = time.monotonic()
        check = HealthCheck(name=name)

        try:
            result = await check_func(**kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000
            check.latency_ms = elapsed_ms

            if result is True:
                check.status = HealthStatus.OK
                check.message = "Healthy"
            elif isinstance(result, str):
                check.status = HealthStatus.DEGRADED
                check.message = result
            else:
                check.status = HealthStatus.FAILING
                check.message = "Check returned False"

        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            check.latency_ms = elapsed_ms
            check.status = HealthStatus.FAILING
            check.message = f"Exception: {e}"
            check.error = traceback.format_exc()

        # Отправить в Healthchecks.io
        if self._hc_url:
            await self.ping(
                name=name,
                status="ok" if check.is_healthy else "fail",
                message=check.message,
            )

        # Отправить алерт в Telegram
        if alert_on_failure and not check.is_healthy:
            await self._send_telegram_alert(check)

        self._record_check(check)
        return check

    async def run_checks(
        self,
        checks: dict[str, Callable[..., Coroutine[Any, Any, bool]]],
    ) -> HealthReport:
        """Запустить несколько проверок параллельно.

        Args:
            checks: Словарь {name: check_function}

        Returns:
            HealthReport с результатами
        """
        tasks = [
            self.check_and_alert(name=name, check_func=func)
            for name, func in checks.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        report = HealthReport()
        for result in results:
            if isinstance(result, Exception):
                report.checks.append(
                    HealthCheck(
                        name="unknown",
                        status=HealthStatus.FAILING,
                        message=f"Check raised exception: {result}",
                        error=str(result),
                    )
                )
            else:
                report.checks.append(result)

        # Отправить общий отчёт если есть проблемы
        if report.overall_status != HealthStatus.OK:
            await self._send_telegram_report(report)

        return report

    async def _send_telegram_alert(self, check: HealthCheck) -> None:
        """Отправить alert в Telegram."""
        if not self._tg_token or not self._tg_chat_id:
            return

        text = (
            f"🔴 *Health Alert*\n\n"
            f"*{check.name}*\n"
            f"Status: `{check.status.value}`\n"
            f"Message: {check.message}\n"
            f"Time: `{check.timestamp}`"
        )

        if check.error:
            text += f"\n\n```\n{check.error[:500]}\n```"

        await self._send_telegram_message(text)

    async def _send_telegram_report(self, report: HealthReport) -> None:
        """Отправить отчёт в Telegram."""
        if not self._tg_token or not self._tg_chat_id:
            return

        text = f"📊 *Health Report*\n\nOverall: `{report.overall_status.value.upper()}`\n"
        text += f"Healthy: {report.healthy_count}/{report.total_count}\n\n"

        for check in report.checks:
            icon = "✅" if check.is_healthy else "❌"
            text += f"{icon} *{check.name}*: {check.message}\n"

        await self._send_telegram_message(text)

    async def _send_telegram_message(self, text: str) -> None:
        """Отправить сообщение в Telegram через Bot API."""
        try:
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            payload = {
                "chat_id": self._tg_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)

            if response.status_code != 200:
                logger.warning(f"Telegram alert failed: HTTP {response.status_code}")
            else:
                logger.debug(f"Telegram alert sent successfully")

        except Exception as e:
            logger.error(f"Telegram alert error: {e}")

    def get_history(self, name: str, last_n: int = 10) -> list[HealthCheck]:
        """Получить историю проверок по имени."""
        history = self._check_history.get(name, [])
        return history[-last_n:]

    def _record_check(self, check: HealthCheck) -> None:
        """Записать проверку в историю."""
        if check.name not in self._check_history:
            self._check_history[check.name] = []
        self._check_history[check.name].append(check)
        # Хранить максимум 100 записей на компонент
        if len(self._check_history[check.name]) > 100:
            self._check_history[check.name] = self._check_history[check.name][-100:]

    @staticmethod
    def _rstrip(s: str, chars: str) -> str:
        """Удалить символы с конца строки."""
        while s and s[-1] in chars:
            s = s[:-1]
        return s
