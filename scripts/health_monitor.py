#!/usr/bin/env python3
"""
Health Monitor для Screenshot-as-a-Service.
Периодически проверяет здоровье сервиса и отправляет алерты.

Использование:
  python3 health_monitor.py                  # однократная проверка
  python3 health_monitor.py --daemon         # фоновый мониторинг
  python3 health_monitor.py --interval 60    # интервал в секундах

Метрики:
  - response_time_ms — время ответа
  - screenshot_time_ms — время создания скриншота
  - cache_hit_rate — процент попаданий в кэш
  - error_rate — процент ошибок
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger


# Метрики
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))
from lab_playwright_kit.metrics import (
    HM_CHECKS,
    HM_LATENCY,
    HM_UPTIME,
    LatencyTimer,
)


# Конфигурация
DEFAULT_URL = os.getenv("SCREENSHOT_SERVICE_URL", "http://localhost:8190")
DEFAULT_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
DEFAULT_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))
DEFAULT_ALERT_WEBHOOK = os.getenv("ALERT_WEBHOOK", "")  # Telegram bot webhook
DEFAULT_LOG_FILE = os.getenv("HEALTH_LOG", "/var/log/screenshot-service-health.jsonl")


@dataclass
class HealthResult:
    """Результат проверки здоровья."""
    timestamp: str
    status: str  # "ok" | "degraded" | "down"
    response_time_ms: float = 0
    screenshot_time_ms: float = 0
    screenshot_success: bool = False
    error: str | None = None


@dataclass
class HealthStats:
    """Статистика за период."""
    total_checks: int = 0
    ok_count: int = 0
    degraded_count: int = 0
    down_count: int = 0
    total_response_ms: float = 0
    total_screenshot_ms: float = 0
    screenshot_count: int = 0
    error_count: int = 0

    @property
    def uptime_pct(self) -> float:
        if self.total_checks == 0:
            return 100.0
        return (self.ok_count / self.total_checks) * 100

    @property
    def avg_response_ms(self) -> float:
        if self.total_checks == 0:
            return 0
        return self.total_response_ms / self.total_checks

    @property
    def avg_screenshot_ms(self) -> float:
        if self.screenshot_count == 0:
            return 0
        return self.total_screenshot_ms / self.screenshot_count

    @property
    def error_rate(self) -> float:
        if self.total_checks == 0:
            return 0
        return (self.error_count / self.total_checks) * 100


class HealthMonitor:
    """Монитор здоровья Screenshot Service."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        timeout: int = DEFAULT_TIMEOUT,
        log_file: str = DEFAULT_LOG_FILE,
        alert_webhook: str = DEFAULT_ALERT_WEBHOOK,
    ):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.log_file = Path(log_file)
        self.alert_webhook = alert_webhook
        self.stats = HealthStats()
        self._last_alert_time = 0
        self._alert_cooldown = 300  # 5 минут между алертами

    async def check_health(self) -> HealthResult:
        """Проверить здоровье сервиса."""
        ts = datetime.utcnow().isoformat()
        start = time.time()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1. Health endpoint
                resp = await client.get(f"{self.url}/health")
                response_ms = (time.time() - start) * 1000

                if resp.status_code != 200:
                    return HealthResult(
                        timestamp=ts,
                        status="down",
                        response_time_ms=response_ms,
                        error=f"HTTP {resp.status_code}",
                    )

                health_data = resp.json()
                if health_data.get("status") != "ok":
                    return HealthResult(
                        timestamp=ts,
                        status="degraded",
                        response_time_ms=response_ms,
                        error=f"Status: {health_data.get('status')}",
                    )

                # 2. Screenshot smoke test
                screenshot_start = time.time()
                try:
                    screenshot_resp = await client.post(
                        f"{self.url}/screenshot",
                        json={"url": "https://example.com", "full_page": False},
                        timeout=30,
                    )
                    screenshot_ms = (time.time() - screenshot_start) * 1000
                    screenshot_ok = screenshot_resp.status_code == 200
                    if screenshot_ok:
                        data = screenshot_resp.json()
                        screenshot_ok = data.get("success", False)
                except Exception as e:
                    screenshot_ms = (time.time() - screenshot_start) * 1000
                    screenshot_ok = False
                    logger.warning(f"Screenshot smoke test failed: {e}")

                # Определить статус
                if not screenshot_ok:
                    status = "degraded"
                elif response_ms > 5000:
                    status = "degraded"
                else:
                    status = "ok"

                return HealthResult(
                    timestamp=ts,
                    status=status,
                    response_time_ms=response_ms,
                    screenshot_time_ms=screenshot_ms,
                    screenshot_success=screenshot_ok,
                )

        except httpx.ConnectError:
            return HealthResult(
                timestamp=ts,
                status="down",
                response_time_ms=(time.time() - start) * 1000,
                error="Connection refused",
            )
        except httpx.TimeoutException:
            return HealthResult(
                timestamp=ts,
                status="down",
                response_time_ms=(time.time() - start) * 1000,
                error="Timeout",
            )
        except Exception as e:
            return HealthResult(
                timestamp=ts,
                status="down",
                response_time_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def update_stats(self, result: HealthResult):
        """Обновить статистику."""
        self.stats.total_checks += 1
        self.stats.total_response_ms += result.response_time_ms

        if result.status == "ok":
            self.stats.ok_count += 1
        elif result.status == "degraded":
            self.stats.degraded_count += 1
        else:
            self.stats.down_count += 1

        if result.screenshot_success:
            self.stats.screenshot_count += 1
            self.stats.total_screenshot_ms += result.screenshot_time_ms

        if result.error:
            self.stats.error_count += 1

    def log_result(self, result: HealthResult):
        """Записать результат в лог."""
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps(asdict(result)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write health log: {e}")

    async def send_alert(self, result: HealthResult):
        """Отправить алерт (Telegram webhook)."""
        if not self.alert_webhook:
            return

        # Cooldown
        now = time.time()
        if now - self._last_alert_time < self._alert_cooldown:
            return
        self._last_alert_time = now

        emoji = "🔴" if result.status == "down" else "🟡"
        text = (
            f"{emoji} **Screenshot Service Alert**\n"
            f"Status: `{result.status}`\n"
            f"Time: `{result.timestamp}`\n"
            f"Response: `{result.response_time_ms:.0f}ms`\n"
        )
        if result.error:
            text += f"Error: `{result.error}`\n"
        text += f"\nUptime: `{self.stats.uptime_pct:.1f}%`"

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    self.alert_webhook,
                    json={"text": text, "parse_mode": "Markdown"},
                    timeout=10,
                )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def run_check(self) -> HealthResult:
        """Выполнить одну проверку."""
        with LatencyTimer(HM_LATENCY, labels={"target": "screenshot-service"}):
            result = await self.check_health()

        self.update_stats(result)
        self.log_result(result)

        # Prometheus метрики
        HM_CHECKS.labels(target="screenshot-service", status=result.status).inc()
        HM_UPTIME.labels(target="screenshot-service").set(self.stats.uptime_pct)

        # Лог
        if result.status == "ok":
            logger.info(
                f"✅ Health OK — {result.response_time_ms:.0f}ms, "
                f"screenshot: {result.screenshot_time_ms:.0f}ms"
            )
        elif result.status == "degraded":
            logger.warning(
                f"⚠️ Degraded — {result.response_time_ms:.0f}ms, "
                f"error: {result.error}"
            )
        else:
            logger.error(
                f"❌ DOWN — {result.response_time_ms:.0f}ms, "
                f"error: {result.error}"
            )

        # Алерт
        if result.status != "ok":
            await self.send_alert(result)

        return result

    async def run_daemon(self, interval: int = DEFAULT_INTERVAL):
        """Запуск в режиме демона."""
        logger.info(f"Starting health monitor — interval={interval}s, url={self.url}")

        while True:
            await self.run_check()
            await asyncio.sleep(interval)

    def print_stats(self):
        """Вывести статистику."""
        print(f"\n{'='*50}")
        print("Health Monitor Statistics")
        print(f"{'='*50}")
        print(f"Total checks:    {self.stats.total_checks}")
        print(f"OK:              {self.stats.ok_count}")
        print(f"Degraded:        {self.stats.degraded_count}")
        print(f"Down:            {self.stats.down_count}")
        print(f"Uptime:          {self.stats.uptime_pct:.1f}%")
        print(f"Avg response:    {self.stats.avg_response_ms:.0f}ms")
        print(f"Avg screenshot:  {self.stats.avg_screenshot_ms:.0f}ms")
        print(f"Error rate:      {self.stats.error_rate:.1f}%")
        print(f"{'='*50}\n")


async def main():
    parser = argparse.ArgumentParser(description="Screenshot Service Health Monitor")
    parser.add_argument("--url", default=DEFAULT_URL, help="Service URL")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Check interval (seconds)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Request timeout")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="Log file path")
    parser.add_argument("--alert-webhook", default=DEFAULT_ALERT_WEBHOOK, help="Alert webhook URL")
    args = parser.parse_args()

    monitor = HealthMonitor(
        url=args.url,
        timeout=args.timeout,
        log_file=args.log_file,
        alert_webhook=args.alert_webhook,
    )

    if args.daemon:
        await monitor.run_daemon(args.interval)
    else:
        result = await monitor.run_check()
        monitor.print_stats()
        sys.exit(0 if result.status == "ok" else 1)


if __name__ == "__main__":
    asyncio.run(main())
