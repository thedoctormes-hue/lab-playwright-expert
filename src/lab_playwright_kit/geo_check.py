"""
Geo-Check модуль для Lab Playwright Kit.

Проверяет геолокацию и IP-адрес через разные VPN-прокси.
Определяет: страну, город, ISP, часовой пояс, язык.

Использование:
    >>> from lab_playwright_kit.geo_check import GeoChecker, GeoResult
    >>> checker = GeoChecker()
    >>> result = await checker.check_ip()
    >>> print(result.country)  # PL
    >>> result = await checker.check_via_proxy("poland")
    >>> print(result.is_match)  # True если IP соответствует ожидаемому
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from .vpn_proxy import VPNProxyManager, VPNProxy


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class GeoResult:
    """Результат проверки геолокации.

    Attributes:
        ip: IP-адрес
        country: Код страны (ISO 3166-1 alpha-2)
        country_name: Полное название страны
        city: Город
        region: Регион/область
        isp: Интернет-провайдер
        timezone: Часовой пояс
        lat: Широта
        lon: Долгота
        languages: Языки страны
        proxy_used: Использованный прокси
        response_ms: Время ответа в мс
        source: Источник данных (ipapi, ipify, etc.)
        raw: Сырые данные ответа
        error: Ошибка (если есть)
    """

    ip: str = ""
    country: str = ""
    country_name: str = ""
    city: str = ""
    region: str = ""
    isp: str = ""
    timezone: str = ""
    lat: float = 0.0
    lon: float = 0.0
    languages: str = ""
    proxy_used: str = "direct"
    response_ms: float = 0.0
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Проверка прошла успешно."""
        return self.error is None and self.ip != ""

    @property
    def is_match(self) -> bool:
        """IP соответствует ожидаемой стране (если прокси указан)."""
        if not self.proxy_used or self.proxy_used == "direct":
            return True
        # Сравнение страны с ожидаемой по прокси
        proxy_countries = {
            "poland": "PL",
            "florida": "US",
        }
        expected = proxy_countries.get(self.proxy_used.lower(), "")
        if expected:
            return self.country.upper() == expected
        return True

    @property
    def summary(self) -> str:
        """Краткое описание результата."""
        if self.error:
            return f"❌ GeoCheck ERROR: {self.error}"
        match_icon = "✅" if self.is_match else "⚠️"
        return (
            f"{match_icon} IP: {self.ip} | {self.country_name} ({self.country}) | "
            f"{self.city} | ISP: {self.isp} | Proxy: {self.proxy_used} | "
            f"{self.response_ms:.0f}ms"
        )

    def __str__(self) -> str:
        return self.summary


@dataclass
class GeoCheckReport:
    """Отчёт по серии geo-check тестов.

    Attributes:
        results: Список результатов
        timestamp: Время создания отчёта
        total_checks: Общее количество проверок
        successful: Успешные проверки
        failed: Неуспешные проверки
        proxy_match: Совпадения прокси
        proxy_mismatch: Несовпадения прокси
    """

    results: list[GeoResult] = field(default_factory=list)
    timestamp: str = field(default="")

    @property
    def total_checks(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> int:
        return sum(1 for r in self.results if r.is_success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.is_success)

    @property
    def proxy_match(self) -> int:
        return sum(1 for r in self.results if r.is_success and r.is_match)

    @property
    def proxy_mismatch(self) -> int:
        return sum(1 for r in self.results if r.is_success and not r.is_match)

    @property
    def avg_response_ms(self) -> float:
        times = [r.response_ms for r in self.results if r.response_ms > 0]
        return sum(times) / len(times) if times else 0.0

    def summary(self) -> str:
        lines = [
            "═══ Geo-Check Report ═══",
            f"Total: {self.total_checks} | OK: {self.successful} | FAIL: {self.failed}",
            f"Proxy match: {self.proxy_match} | Mismatch: {self.proxy_mismatch}",
            f"Avg response: {self.avg_response_ms:.0f}ms",
            "",
        ]
        for r in self.results:
            lines.append(f"  {r.summary}")
        return "\n".join(lines)


# ─── Geo Checker ─────────────────────────────────────────────────────────────

class GeoChecker:
    """Проверка геолокации через внешние API.

    Поддерживает несколько источников данных:
    - ipapi.co (основной, 100 req/day free)
    - ipify.org + ipapi.co (резервный)
    - httpbin.org/ip (fallback, только IP)

    Использование:
        >>> checker = GeoChecker()
        >>> result = await checker.check_ip()
        >>> print(result.country)
        >>> report = await checker.check_all_proxies()
        >>> print(report.summary())
    """

    # API endpoints для определения геолокации
    GEO_APIS = [
        {
            "name": "ipapi.co",
            "url": "https://ipapi.co/json/",
            "fields": {
                "ip": "ip",
                "country": "country_code",
                "country_name": "country_name",
                "city": "city",
                "region": "region",
                "isp": "org",
                "timezone": "timezone",
                "lat": "latitude",
                "lon": "longitude",
                "languages": "languages",
            },
        },
        {
            "name": "ipwho.is",
            "url": "https://ipwho.is/",
            "fields": {
                "ip": "ip",
                "country": "country_code",
                "country_name": "country",
                "city": "city",
                "region": "region",
                "isp": "connection",
                "timezone": "timezone.id",
                "lat": "latitude",
                "lon": "longitude",
                "languages": "",
            },
        },
    ]

    def __init__(
        self,
        timeout: float = 10.0,
        proxy_manager: VPNProxyManager | None = None,
    ):
        self._timeout = timeout
        self._proxy_manager = proxy_manager or VPNProxyManager()

    async def check_ip(
        self,
        proxy: str | VPNProxy | None = None,
        source: str = "ipapi.co",
    ) -> GeoResult:
        """Проверить IP и геолокацию.

        Args:
            proxy: Прокси (VPNProxy, URL или None для direct)
            source: Источник данных (ipapi.co, ipwho.is)

        Returns:
            GeoResult с данными о геолокации
        """
        proxy_name = "direct"
        proxy_url = None

        if isinstance(proxy, VPNProxy):
            proxy_name = proxy.name
            proxy_url = proxy.server
        elif isinstance(proxy, str):
            proxy_name = proxy
            p = self._proxy_manager.get(proxy)
            proxy_url = p.server if p else None
            if proxy_url is None and proxy.lower() != "direct":
                # Может это URL напрямую
                if proxy.startswith(("http://", "https://", "socks5://")):
                    proxy_url = proxy
                    proxy_name = "custom"

        # Найти API конфигуцию
        api_config = None
        for api in self.GEO_APIS:
            if api["name"] == source:
                api_config = api
                break
        if api_config is None:
            api_config = self.GEO_APIS[0]

        result = GeoResult(proxy_used=proxy_name, source=source)

        try:
            start = time.monotonic()

            client_kwargs: dict[str, Any] = {"timeout": self._timeout}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(api_config["url"])

            elapsed_ms = (time.monotonic() - start) * 1000
            result.response_ms = elapsed_ms

            if response.status_code != 200:
                result.error = f"HTTP {response.status_code}"
                return result

            data = response.json()
            result.raw = data

            # Маппинг полей
            fields = api_config["fields"]
            result.ip = self._extract_field(data, fields.get("ip", "ip")) or ""
            result.country = self._extract_field(data, fields.get("country", "country_code")) or ""
            result.country_name = self._extract_field(data, fields.get("country_name", "country")) or ""
            result.city = self._extract_field(data, fields.get("city", "city")) or ""
            result.region = self._extract_field(data, fields.get("region", "region")) or ""
            result.timezone = self._extract_field(data, fields.get("timezone", "timezone")) or ""

            # ISP может быть в разных полях
            isp_val = self._extract_field(data, fields.get("isp", "org"))
            if not isp_val:
                isp_val = self._extract_field(data, "connection", nested_key="org")
            result.isp = isp_val or ""

            # Координаты
            lat_val = self._extract_field(data, fields.get("lat", "latitude"))
            lon_val = self._extract_field(data, fields.get("lon", "longitude"))
            if lat_val:
                try:
                    result.lat = float(lat_val)
                except (ValueError, TypeError):
                    pass
            if lon_val:
                try:
                    result.lon = float(lon_val)
                except (ValueError, TypeError):
                    pass

            logger.debug(f"GeoCheck: {result.summary}")

        except httpx.TimeoutException:
            result.error = "Timeout"
            logger.warning(f"GeoCheck timeout via {proxy_name}")
        except httpx.ConnectError as e:
            result.error = f"Connection error: {e}"
            logger.warning(f"GeoCheck connection error via {proxy_name}: {e}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"GeoCheck error via {proxy_name}: {e}")

        return result

    async def check_via_proxy(self, proxy_name: str) -> GeoResult:
        """Проверить геолокацию через конкретный прокси.

        Args:
            proxy_name: Имя прокси (poland, florida, direct)

        Returns:
            GeoResult
        """
        proxy = self._proxy_manager.get(proxy_name)
        if proxy is None:
            return GeoResult(
                error=f"Proxy '{proxy_name}' not found",
                proxy_used=proxy_name,
            )
        return await self.check_ip(proxy=proxy)

    async def check_all_proxies(self) -> GeoCheckReport:
        """Проверить геолокацию через все доступные прокси.

        Returns:
            GeoCheckReport с результатами для всех прокси
        """
        from datetime import datetime, timezone

        report = GeoCheckReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        proxies = self._proxy_manager.list_all()
        logger.info(f"GeoCheck: checking {len(proxies)} proxies...")

        tasks = [self.check_via_proxy(p.name) for p in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                report.results.append(GeoResult(error=str(result)))
            else:
                report.results.append(result)

        logger.info(
            f"GeoCheck complete: {report.successful}/{report.total_checks} OK, "
            f"{report.proxy_match} proxy matches"
        )
        return report

    async def verify_proxy_geo(
        self,
        proxy_name: str,
        expected_country: str,
    ) -> bool:
        """Проверить что прокси выдаёт ожидаемую страну.

        Args:
            proxy_name: Имя прокси
            expected_country: Ожидаемый код страны (PL, US)

        Returns:
            True если страна совпадает
        """
        result = await self.check_via_proxy(proxy_name)
        if not result.is_success:
            logger.warning(f"GeoCheck: {proxy_name} failed — {result.error}")
            return False

        match = result.country.upper() == expected_country.upper()
        if match:
            logger.info(f"GeoCheck: {proxy_name} → {result.country} ✅")
        else:
            logger.warning(
                f"GeoCheck: {proxy_name} → {result.country} "
                f"(expected {expected_country}) ⚠️"
            )
        return match

    @staticmethod
    def _extract_field(data: dict, field: str, nested_key: str | None = None) -> Any:
        """Извлечь поле из словаря, поддержка вложенных полей через точку."""
        if not field:
            return None

        keys = field.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            if current is None:
                return None

        if nested_key and isinstance(current, dict):
            return current.get(nested_key)

        return current
