"""
Proxy Rotation модуль: автоматическая ротация прокси-серверов.

Поддерживает:
  - Протоколы: http, https, socks5
  - Стратегии ротации: round-robin, random
  - Health check прокси (ping через httpx)
  - Отслеживание здоровья: mark_failed(), mark_success()
  - Автоматическое исключение нерабочих прокси

Example:
    >>> rotator = ProxyRotator(strategy="round_robin")
    >>> rotator.add_proxy("http://proxy1:8080")
    >>> rotator.add_proxy("socks5://proxy2:1080")
    >>> proxy = rotator.get_next()
    >>> rotator.mark_success(proxy)
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx
from loguru import logger


class ProxyProtocol(str, Enum):
    """Поддерживаемые протоколы прокси."""
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class RotationStrategy(str, Enum):
    """Стратегии ротации прокси."""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"


@dataclass
class ProxyInfo:
    """Информация о прокси-сервере.

    Attributes:
        url: Полный URL прокси (например, http://proxy:8080)
        protocol: Протокол прокси
        host: Хост прокси
        port: Порт прокси
        username: Имя пользователя (опционально)
        password: Пароль (опционально)
        weight: Вес для weighted round-robin (по умолчанию 1)
        max_failures: Максимальное число неудач перед исключением
        cooldown_seconds: Время блокировки после достижения max_failures
    """

    url: str
    protocol: ProxyProtocol
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    weight: int = 1
    max_failures: int = 3
    cooldown_seconds: int = 300

    # Внутренние поля (не для конструктора)
    failures: int = field(default=0, repr=False)
    successes: int = field(default=0, repr=False)
    last_used: float = field(default=0.0, repr=False)
    last_checked: float = field(default=0.0, repr=False)
    is_healthy: bool = field(default=True, repr=False)
    cooldown_until: float = field(default=0.0, repr=False)
    avg_latency_ms: float = field(default=0.0, repr=False)

    @property
    def is_available(self) -> bool:
        """Прокси доступен для использования."""
        if not self.is_healthy:
            # Проверить, прошло ли время cooldown
            if time.monotonic() < self.cooldown_until:
                return False
            # Cooldown прошёл — сбросить здоровье для повторной проверки
            self.is_healthy = True
            self.failures = 0
            return True
        return True

    @property
    def playwright_format(self) -> dict[str, str]:
        """Формат прокси для Playwright."""
        result: dict[str, str] = {"server": self.url}
        if self.username:
            result["username"] = self.username
        if self.password:
            result["password"] = self.password
        return result

    def __str__(self) -> str:
        auth = f"{self.username}@" if self.username else ""
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"


class ProxyRotator:
    """Менеджер ротации прокси-серверов.

    Поддерживает round-robin и random стратегии,
    health check, автоматическое исключение нерабочих прокси.

    Example:
        >>> rotator = ProxyRotator(strategy="round_robin")
        >>> rotator.add_proxy("http://proxy1:8080")
        >>> rotator.add_proxy("socks5://proxy2:1080")
        >>> proxy = rotator.get_next()
        >>> if proxy:
        ...     # Использовать прокси
        ...     rotator.mark_success(proxy)
    """

    def __init__(
        self,
        strategy: str = "round_robin",
        health_check_url: str = "https://httpbin.org/ip",
        health_check_timeout: int = 10,
    ):
        self._strategy = RotationStrategy(strategy)
        self._health_check_url = health_check_url
        self._health_check_timeout = health_check_timeout
        self._proxies: list[ProxyInfo] = []
        self._round_robin_index: int = 0
        self._lock = asyncio.Lock()

    def add_proxy(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
        weight: int = 1,
        max_failures: int = 3,
        cooldown_seconds: int = 300,
    ) -> ProxyInfo:
        """Добавить прокси в пул.

        Args:
            url: URL прокси (например, http://proxy:8080)
            username: Имя пользователя (опционально)
            password: Пароль (опционально)
            weight: Вес для weighted стратегии
            max_failures: Максимум неудач перед исключением
            cooldown_seconds: Время блокировки после max_failures

        Returns:
            Созданный ProxyInfo объект

        Raises:
            ValueError: Если URL имеет невалидный формат или протокол
        """
        protocol = self._parse_protocol(url)
        host, port = self._parse_host_port(url)

        proxy = ProxyInfo(
            url=url,
            protocol=protocol,
            host=host,
            port=port,
            username=username,
            password=password,
            weight=weight,
            max_failures=max_failures,
            cooldown_seconds=cooldown_seconds,
        )

        self._proxies.append(proxy)
        logger.info(f"Proxy added: {proxy} (total: {len(self._proxies)})")
        return proxy

    def get_next(self) -> ProxyInfo | None:
        """Получить следующий прокси согласно стратегии.

        Returns:
            ProxyInfo или None если нет доступных прокси
        """
        available = [p for p in self._proxies if p.is_available]
        if not available:
            logger.warning("No available proxies")
            return None

        if self._strategy == RotationStrategy.ROUND_ROBIN:
            return self._get_round_robin(available)
        elif self._strategy == RotationStrategy.RANDOM:
            return self._get_random(available)
        else:
            return available[0]

    def mark_failed(self, proxy: ProxyInfo) -> None:
        """Пометить прокси как нерабочий.

        Увеличивает счётчик неудач. При достижении max_failures
        прокси исключается из ротации на cooldown_seconds.

        Args:
            proxy: ProxyInfo объект для пометки
        """
        proxy.failures += 1
        proxy.last_used = time.monotonic()

        if proxy.failures >= proxy.max_failures:
            proxy.is_healthy = False
            proxy.cooldown_until = time.monotonic() + proxy.cooldown_seconds
            logger.warning(
                f"Proxy {proxy} marked unhealthy after {proxy.failures} failures. "
                f"Cooldown until {proxy.cooldown_until:.0f}s"
            )
        else:
            logger.debug(
                f"Proxy {proxy} failure #{proxy.failures}/{proxy.max_failures}"
            )

    def mark_success(self, proxy: ProxyInfo, latency_ms: float = 0.0) -> None:
        """Пометить прокси как рабочий.

        Увеличивает счётчик успехов. Сбрасывает счётчик неудач.
        Обновляет среднюю латентность.

        Args:
            proxy: ProxyInfo объект для пометки
            latency_ms: Латентность последнего запроса в мс
        """
        proxy.successes += 1
        proxy.last_used = time.monotonic()

        # Сбросить неудачи при успехе
        if proxy.failures > 0:
            proxy.failures = 0
            logger.debug(f"Proxy {proxy} failures reset after success")

        # Обновить среднюю латентность (скользящее среднее)
        if latency_ms > 0:
            if proxy.avg_latency_ms == 0:
                proxy.avg_latency_ms = latency_ms
            else:
                proxy.avg_latency_ms = 0.7 * proxy.avg_latency_ms + 0.3 * latency_ms

    async def health_check(
        self,
        proxy: ProxyInfo | None = None,
    ) -> dict[str, bool]:
        """Проверить здоровье прокси.

        Отправляет HTTP-запрос через прокси и проверяет ответ.
        Если proxy=None — проверить все прокси в пуле.

        Args:
            proxy: Конкретный прокси для проверки, или None для всех

        Returns:
            Словарь {proxy_url: is_healthy}

        Example:
            >>> results = await rotator.health_check()
            >>> for url, healthy in results.items():
            ...     print(f"{url}: {'OK' if healthy else 'FAIL'}")
        """
        targets = [proxy] if proxy else self._proxies
        results: dict[str, bool] = {}

        for p in targets:
            if p is None:
                continue
            try:
                start = time.monotonic()
                async with httpx.AsyncClient(
                    proxy=p.url,
                    timeout=self._health_check_timeout,
                ) as client:
                    response = await client.get(self._health_check_url)
                elapsed_ms = (time.monotonic() - start) * 1000

                is_healthy = response.status_code == 200
                p.last_checked = time.monotonic()

                if is_healthy:
                    self.mark_success(p, elapsed_ms)
                else:
                    self.mark_failed(p)

                results[p.url] = is_healthy
                logger.debug(
                    f"Health check {p}: {'OK' if is_healthy else 'FAIL'} "
                    f"({elapsed_ms:.0f}ms)"
                )
            except Exception as e:
                self.mark_failed(p)
                results[p.url] = False
                logger.debug(f"Health check {p}: FAIL ({e})")

        return results

    async def health_check_all(self) -> dict[str, bool]:
        """Проверить здоровье всех прокси в пуле.

        Returns:
            Словарь {proxy_url: is_healthy}
        """
        return await self.health_check(proxy=None)

    def remove_proxy(self, url: str) -> bool:
        """Удалить прокси из пула.

        Args:
            url: URL прокси для удаления

        Returns:
            True если прокси был найден и удалён
        """
        for i, p in enumerate(self._proxies):
            if p.url == url:
                self._proxies.pop(i)
                # Корректировать round-robin индекс
                if self._round_robin_index >= len(self._proxies):
                    self._round_robin_index = 0
                logger.info(f"Proxy removed: {url} (remaining: {len(self._proxies)})")
                return True
        logger.warning(f"Proxy not found for removal: {url}")
        return False

    def reset(self) -> None:
        """Сбросить все прокси в начальное состояние.

        Сбрасывает счётчики неудач/успехов, восстанавливает
        здоровье всех прокси.
        """
        for p in self._proxies:
            p.failures = 0
            p.successes = 0
            p.is_healthy = True
            p.cooldown_until = 0.0
            p.avg_latency_ms = 0.0
        self._round_robin_index = 0
        logger.info(f"All {len(self._proxies)} proxies reset")

    @property
    def total_count(self) -> int:
        """Общее количество прокси в пуле."""
        return len(self._proxies)

    @property
    def healthy_count(self) -> int:
        """Количество здоровых прокси."""
        return sum(1 for p in self._proxies if p.is_available)

    @property
    def unhealthy_count(self) -> int:
        """Количество нездоровых прокси."""
        return self.total_count - self.healthy_count

    @property
    def proxies(self) -> list[ProxyInfo]:
        """Список всех прокси (копия)."""
        return list(self._proxies)

    @property
    def healthy_proxies(self) -> list[ProxyInfo]:
        """Список здоровых прокси."""
        return [p for p in self._proxies if p.is_available]

    def get_stats(self) -> dict[str, int | float]:
        """Получить статистику пула прокси.

        Returns:
            Словарь с ключами: total, healthy, unhealthy,
            total_successes, total_failures, avg_latency_ms
        """
        total_successes = sum(p.successes for p in self._proxies)
        total_failures = sum(p.failures for p in self._proxies)
        latencies = [p.avg_latency_ms for p in self._proxies if p.avg_latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "total": self.total_count,
            "healthy": self.healthy_count,
            "unhealthy": self.unhealthy_count,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "avg_latency_ms": round(avg_latency, 2),
        }

    # ─── Internal methods ──────────────────────────────────────────────────────

    def _get_round_robin(self, available: list[ProxyInfo]) -> ProxyInfo:
        """Round-robin выбор прокси."""
        if self._round_robin_index >= len(available):
            self._round_robin_index = 0

        proxy = available[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(available)
        proxy.last_used = time.monotonic()
        return proxy

    def _get_random(self, available: list[ProxyInfo]) -> ProxyInfo:
        """Random выбор прокси."""
        proxy = random.choice(available)
        proxy.last_used = time.monotonic()
        return proxy

    @staticmethod
    def _parse_protocol(url: str) -> ProxyProtocol:
        """Извлечь протокол из URL прокси.

        Args:
            url: URL прокси

        Returns:
            ProxyProtocol

        Raises:
            ValueError: Если протокол не поддерживается
        """
        url_lower = url.lower().strip()
        for proto in ProxyProtocol:
            if url_lower.startswith(f"{proto.value}://"):
                return proto
        raise ValueError(
            f"Unsupported proxy protocol in URL: {url}. "
            f"Supported: {', '.join(p.value for p in ProxyProtocol)}"
        )

    @staticmethod
    def _parse_host_port(url: str) -> tuple[str, int]:
        """Извлечь хост и порт из URL прокси.

        Args:
            url: URL прокси

        Returns:
            Кортеж (host, port)

        Raises:
            ValueError: Если URL имеет невалидный формат
        """
        # Убрать protocol://
        without_protocol = url.split("://", 1)[1] if "://" in url else url

        # Убрать auth (user:pass@)
        if "@" in without_protocol:
            without_protocol = without_protocol.split("@", 1)[1]

        # Убрать path
        without_protocol = without_protocol.split("/")[0]

        # Парсинг host:port
        if ":" not in without_protocol:
            raise ValueError(
                f"Proxy URL must include port: {url}. "
                f"Expected format: protocol://host:port"
            )

        parts = without_protocol.rsplit(":", 1)
        host = parts[0]
        try:
            port = int(parts[1])
        except (ValueError, IndexError):
            raise ValueError(f"Invalid port in proxy URL: {url}")

        if not 1 <= port <= 65535:
            raise ValueError(f"Port out of range (1-65535): {port}")

        return host, port
