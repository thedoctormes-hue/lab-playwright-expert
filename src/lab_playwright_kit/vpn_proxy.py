"""
VPN Proxy Integration модуль для Lab Playwright Kit.

Предоставляет управление VPN-прокси для обхода DPI и геоблокировки.
Поддерживает VLESS+REALITY туннели через локальные SOCKS5-порты.

Схема подключения:
    Client → Local SOCKS5 → VPN Server (VLESS+REALITY) → Target

Использование:
    >>> from lab_playwright_kit.vpn_proxy import VPNProxyManager
    >>> manager = VPNProxyManager.from_yaml("config/vpn_proxies.yaml")
    >>> proxy = manager.get("poland")
    >>> print(proxy.server)  # socks5://127.0.0.1:10808
"""
from __future__ import annotations

import random
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


@dataclass
class VPNProxy:
    """Конфигурация VPN-прокси.

    Attributes:
        name: Имя прокси (poland, florida, direct)
        server: URL прокси-сервера (socks5://...) или None для direct
        country: Код страны выхода (PL, US, DIRECT)
        exit_ip: IP-адрес выхода
        protocol: Протокол (VLESS+REALITY, DIRECT)
        description: Описание прокси
    """

    name: str
    server: str | None
    country: str
    exit_ip: str
    protocol: str = "VLESS+REALITY"
    description: str = ""

    @property
    def is_direct(self) -> bool:
        """Прямое подключение (без прокси)."""
        return self.server is None

    @property
    def host_port(self) -> tuple[str, int] | None:
        """Парсит server на (host, port). Возвращает None для direct."""
        if self.is_direct or not self.server:
            return None
        try:
            # socks5://host:port → (host, port)
            without_proto = self.server.split("://", 1)[1] if "://" in self.server else self.server
            if "@" in without_proto:
                without_proto = without_proto.split("@", 1)[1]
            parts = without_proto.rsplit(":", 1)
            return parts[0], int(parts[1])
        except (ValueError, IndexError):
            return None

    def to_playwright_format(self) -> dict[str, str] | None:
        """Формат прокси для Playwright BrowserManager.

        Returns:
            Dict с ключом 'server' (и опционально 'username', 'password')
            или None для прямого подключения.
        """
        if self.is_direct or not self.server:
            return None
        return {"server": self.server}

    def __str__(self) -> str:
        if self.is_direct:
            return f"{self.name} (DIRECT, exit_ip={self.exit_ip})"
        return f"{self.name} ({self.server}, {self.country}, exit_ip={self.exit_ip})"


class VPNProxyManager:
    """Менеджер VPN-прокси: загрузка, выбор, health check.

    Загружает конфигурацию из YAML или использует встроенные дефолтные прокси.

    Использование:
        >>> manager = VPNProxyManager()  # дефолтные прокси
        >>> manager = VPNProxyManager.from_yaml("config/vpn_proxies.yaml")
        >>> proxy = manager.get("poland")
        >>> healthy = manager.get_healthy_proxy()
    """

    # Встроенные дефолтные прокси (соответствуют config/vpn_proxies.yaml)
    PROXIES: list[dict[str, Any]] = [
        {
            "name": "poland",
            "server": "socks5://127.0.0.1:10808",
            "country": "PL",
            "exit_ip": "78.17.43.205",
            "protocol": "VLESS+REALITY",
            "description": "Warsaw server — VLESS+REALITY, xhttp obfuscation",
        },
        {
            "name": "florida",
            "server": "socks5://127.0.0.1:63567",
            "country": "US",
            "exit_ip": "104.253.1.210",
            "protocol": "VLESS+REALITY",
            "description": "Florida server — VLESS+REALITY, xhttp obfuscation",
        },
        {
            "name": "direct",
            "server": None,
            "country": "DIRECT",
            "exit_ip": "89.169.4.51",
            "protocol": "DIRECT",
            "description": "Прямое подключение без прокси",
        },
    ]

    def __init__(self, proxies: list[dict[str, Any]] | None = None):
        """Инициализация менеджера.

        Args:
            proxies: Список словарей с конфигурацией прокси.
                     Если None — используются PROXIES по умолчанию.
        """
        raw = proxies if proxies is not None else self.PROXIES
        self._proxies: dict[str, VPNProxy] = {}
        for p in raw:
            proxy = VPNProxy(
                name=p["name"],
                server=p.get("server"),
                country=p.get("country", "UNKNOWN"),
                exit_ip=p.get("exit_ip", "0.0.0.0"),
                protocol=p.get("protocol", "VLESS+REALITY"),
                description=p.get("description", ""),
            )
            self._proxies[proxy.name] = proxy
        logger.debug(f"VPNProxyManager initialized with {len(self._proxies)} proxies")

    @classmethod
    def from_yaml(cls, path: str | Path) -> VPNProxyManager:
        """Загрузить конфигурацию прокси из YAML-файла.

        Args:
            path: Путь к YAML-файлу с секцией 'proxies'.

        Returns:
            Новый экземпляр VPNProxyManager.

        Raises:
            FileNotFoundError: Если файл не найден.
            KeyError: Если в файле нет секции 'proxies'.
            yaml.YAMLError: Если файл невалидный YAML.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"VPN proxy config not found: {path}")

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "proxies" not in data:
            raise KeyError(f"Invalid VPN proxy config: missing 'proxies' key in {path}")

        logger.info(f"Loaded VPN proxy config from {path} ({len(data['proxies'])} proxies)")
        return cls(proxies=data["proxies"])

    def get(self, name: str) -> VPNProxy | None:
        """Получить прокси по имени.

        Args:
            name: Имя прокси (poland, florida, direct).

        Returns:
            VPNProxy или None если не найден.
        """
        proxy = self._proxies.get(name)
        if proxy is None:
            logger.warning(f"Proxy '{name}' not found. Available: {list(self._proxies.keys())}")
        return proxy

    def get_by_country(self, country: str) -> VPNProxy | None:
        """Получить прокси по коду страны.

        Args:
            country: Код страны (PL, US, DIRECT).

        Returns:
            Первый найденный VPNProxy или None.
        """
        country_upper = country.upper()
        for proxy in self._proxies.values():
            if proxy.country.upper() == country_upper:
                return proxy
        logger.warning(f"No proxy for country '{country}'")
        return None

    def get_random(self) -> VPNProxy | None:
        """Получить случайный прокси (кроме direct).

        Returns:
            Случайный VPNProxy или None если нет прокси.
        """
        non_direct = [p for p in self._proxies.values() if not p.is_direct]
        if not non_direct:
            logger.warning("No non-direct proxies available")
            return None
        return random.choice(non_direct)

    def list_all(self) -> list[VPNProxy]:
        """Список всех прокси.

        Returns:
            Список VPNProxy.
        """
        return list(self._proxies.values())

    @staticmethod
    def health_check(proxy: VPNProxy, timeout: float = 5.0) -> bool:
        """Проверить жив ли прокси (TCP connect).

        Пытается установить TCP-соединение с host:port прокси.
        Для direct всегда возвращает True.

        Args:
            proxy: VPNProxy для проверки.
            timeout: Таймаут соединения в секундах.

        Returns:
            True если прокси отвечает.
        """
        if proxy.is_direct:
            logger.debug("health_check: direct connection — always healthy")
            return True

        parsed = proxy.host_port
        if parsed is None:
            logger.warning(f"health_check: cannot parse server URL for {proxy.name}")
            return False

        host, port = parsed
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            logger.debug(f"health_check: {proxy.name} ({host}:{port}) — OK")
            return True
        except (socket.timeout, OSError) as e:
            logger.warning(f"health_check: {proxy.name} ({host}:{port}) — FAIL ({e})")
            return False

    def get_healthy_proxy(self, prefer: str | None = None) -> VPNProxy | None:
        """Получить первый здоровый проверенный прокси.

        Если указан prefer — проверяет сначала его.
        Затем перебирает все прокси (кроме direct) по порядку.

        Args:
            prefer: Имя предпочтительного прокси (опционально).

        Returns:
            Первый здоровый VPNProxy или None.
        """
        # Сначала проверить предпочтительный
        if prefer:
            proxy = self.get(prefer)
            if proxy and self.health_check(proxy):
                return proxy

        # Перебрать все (кроме direct)
        for name, proxy in self._proxies.items():
            if proxy.is_direct:
                continue
            if self.health_check(proxy):
                return proxy

        # Fallback на direct
        direct = self.get("direct")
        if direct:
            logger.info("All VPN proxies down — falling back to direct")
            return direct

        return None

    def __len__(self) -> int:
        return len(self._proxies)

    def __contains__(self, name: str) -> bool:
        return name in self._proxies

    def __repr__(self) -> str:
        names = ", ".join(self._proxies.keys())
        return f"VPNProxyManager([{names}])"
