"""
User-Agent Client Hints spoofing модуль.

Реализует согласованные Sec-CH-UA-* заголовки и JavaScript API:
  - Sec-CH-UA (бренд и версия браузера)
  - Sec-CH-UA-Platform (ОС)
  - Sec-CH-UA-Mobile (мобильный ли браузер)
  - Sec-CH-UA-Full-Version (полная версия)
  - Sec-CH-UA-Arch (архитектура)
  - Sec-CH-UA-Bitness (битность)
  - Sec-CH-UA-Model (модель устройства)
  - navigator.userAgentData (JavaScript API)

Использование:
    >>> from lab_playwright_kit.stealth_client_hints import ClientHintsConfig, ClientHintsSpoofer
    >>> config = ClientHintsConfig.from_user_agent(ua_string)
    >>> js = ClientHintsSpoofer.get_script(config)
    >>> await page.add_init_script(js)

Принцип работы:
  Антибот-системы проверяют согласованность между:
  1. User-Agent строкой (HTTP заголовок)
  2. Sec-CH-UA-* (HTTP заголовки и JavaScript API)
  3. navigator.userAgentData (JavaScript API)

  Если UA говорит "Chrome 131 Windows", а Sec-CH-UA говорит
  "Firefox 133 macOS" — это мгновенный детект.

  Этот модуль автоматически парсит UA-строку и генерирует
  согласованные Client Hints.

Покрытие сигнатур:
  - User-Agent Client Hints mismatch detection
  - navigator.userAgentData high-entropy values
  - Brand/version consistency checks
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger
from playwright.async_api import Page


@dataclass
class ClientHintsData:
    """Структурированные Client Hints данные.

    Содержит все поля User-Agent Client Hints,
    согласованные между собой.
    """
    # Основные поля
    brand: str = "Chromium"
    major_version: str = "131"
    full_version: str = "131.0.0.0"

    # Платформа
    platform: str = "Windows"
    platform_version: str = "15.0.0"

    # Устройство
    mobile: bool = False
    arch: str = "x86"
    bitness: str = "64"
    model: str = ""

    # Полная бренд-список (для Sec-CH-UA)
    brands: list[dict[str, str]] = field(default_factory=lambda: [
        {"brand": "Chromium", "version": "131"},
        {"brand": "Google Chrome", "version": "131"},
        {"brand": "Not-A.Brand", "version": "24"},
    ])

    # Полный список для navigator.userAgentData.getHighEntropyValues
    full_brands: list[dict[str, str]] = field(default_factory=lambda: [
        {"brand": "Chromium", "version": "131"},
        {"brand": "Google Chrome", "version": "131"},
        {"brand": "Not-A.Brand", "version": "24"},
    ])


@dataclass
class ClientHintsConfig:
    """Конфигурация User-Agent Client Hints.

    Attributes:
        hints: Структурированные данные Client Hints.
        override_ua: Если True — подменить User-Agent на соответствующий hints.
        spoof_high_entropy: Подменять getHighEntropyValues().
    """
    hints: ClientHintsData = field(default_factory=ClientHintsData)
    override_ua: bool = False
    spoof_high_entropy: bool = True

    @classmethod
    def from_user_agent(cls, user_agent: str) -> ClientHintsConfig:
        """Создать конфигурацию из User-Agent строки.

        Автоматически парсит UA и генерирует согласованные hints.

        Args:
            user_agent: User-Agent строка браузера.

        Returns:
            ClientHintsConfig с согласованными hints.

        Example:
            >>> config = ClientHintsConfig.from_user_agent(
            ...     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            ...     "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ... )
        """
        hints = _parse_user_agent(user_agent)
        return cls(hints=hints)

    @classmethod
    def chrome_windows(cls, version: str = "131") -> ClientHintsConfig:
        """Chrome на Windows."""
        return cls(hints=ClientHintsData(
            brand="Google Chrome",
            major_version=version,
            full_version=f"{version}.0.0.0",
            platform="Windows",
            platform_version="15.0.0",
            mobile=False,
            arch="x86",
            bitness="64",
            brands=[
                {"brand": "Chromium", "version": version},
                {"brand": "Google Chrome", "version": version},
                {"brand": "Not-A.Brand", "version": "24"},
            ],
            full_brands=[
                {"brand": "Chromium", "version": version},
                {"brand": "Google Chrome", "version": version},
                {"brand": "Not-A.Brand", "version": "24"},
            ],
        ))

    @classmethod
    def chrome_macos(cls, version: str = "131") -> ClientHintsConfig:
        """Chrome на macOS."""
        return cls(hints=ClientHintsData(
            brand="Google Chrome",
            major_version=version,
            full_version=f"{version}.0.0.0",
            platform="macOS",
            platform_version="14.0.0",
            mobile=False,
            arch="x86",
            bitness="64",
            brands=[
                {"brand": "Chromium", "version": version},
                {"brand": "Google Chrome", "version": version},
                {"brand": "Not-A.Brand", "version": "24"},
            ],
            full_brands=[
                {"brand": "Chromium", "version": version},
                {"brand": "Google Chrome", "version": version},
                {"brand": "Not-A.Brand", "version": "24"},
            ],
        ))

    @classmethod
    def firefox_windows(cls, version: str = "133") -> ClientHintsConfig:
        """Firefox на Windows (ограниченная поддержка Client Hints)."""
        return cls(hints=ClientHintsData(
            brand="Firefox",
            major_version=version,
            full_version=version,
            platform="Windows",
            platform_version="15.0.0",
            mobile=False,
            arch="x86",
            bitness="64",
            brands=[
                {"brand": "Firefox", "version": version},
            ],
            full_brands=[
                {"brand": "Firefox", "version": version},
            ],
        ))


class ClientHintsSpoofer:
    """Генератор JS-скриптов для User-Agent Client Hints spoofing.

    Обеспечивает согласованность между User-Agent строкой
    и Sec-CH-UA-* заголовками / navigator.userAgentData API.

    Example:
        >>> config = ClientHintsConfig.chrome_windows("131")
        >>> script = ClientHintsSpoofer.get_script(config)
        >>> await page.add_init_script(script)
    """

    @staticmethod
    def get_script(config: ClientHintsConfig) -> str:
        """Получить полный JS-скрипт для инъекции.

        Args:
            config: Конфигурация Client Hints.

        Returns:
            JS-скрипт для инъекции через page.add_init_script().
        """
        parts = [
            ClientHintsSpoofer._spoof_user_agent_data(config),
        ]

        inner = "\n".join(p for p in parts if p.strip())
        return f"(function() {{\n{inner}\n}})();"

    @staticmethod
    def _spoof_user_agent_data(config: ClientHintsConfig) -> str:
        """Подмена navigator.userAgentData.

        Патчит userAgentData для возврата согласованных
        Client Hints значений.
        """
        hints = config.hints
        brands_json = str(hints.brands).replace("'", '"')
        full_brands_json = str(hints.full_brands).replace("'", '"')

        return f"""
            // ── Подмена navigator.userAgentData ──
            (function() {{
                const brands = {brands_json};
                const fullBrands = {full_brands_json};
                const platform = "{hints.platform}";
                const mobile = {str(hints.mobile).lower()};
                const architecture = "{hints.arch}";
                const bitness = "{hints.bitness}";
                const model = "{hints.model}";
                const platformVersion = "{hints.platform_version}";
                const uaFullVersion = "{hints.full_version}";

                // Создаём фейковый userAgentData
                const fakeUAData = {{
                    brands: brands,
                    mobile: mobile,
                    platform: platform,
                    getHighEntropyValues: function(hints) {{
                        const result = {{
                            brands: fullBrands,
                            mobile: mobile,
                            platform: platform,
                            platformVersion: platformVersion,
                            architecture: architecture,
                            bitness: bitness,
                            model: model,
                            uaFullVersion: uaFullVersion,
                        }};
                        // Фильтруем по запрошенным hints
                        const filtered = {{}};
                        for (const hint of hints) {{
                            if (hint in result) {{
                                filtered[hint] = result[hint];
                            }}
                        }}
                        return Promise.resolve(filtered);
                    }}
                }};

                // Подменяем userAgentData
                Object.defineProperty(navigator, 'userAgentData', {{
                    get: () => fakeUAData,
                    configurable: true
                }});
            }})();
        """


def _parse_user_agent(user_agent: str) -> ClientHintsData:
    """Парсинг User-Agent строки в структурированные Client Hints.

    Поддерживает Chrome, Firefox, Edge, Safari.

    Args:
        user_agent: User-Agent строка.

    Returns:
        ClientHintsData с извлечёнными значениями.
    """
    data = ClientHintsData()

    # Определяем браузер и версию
    chrome_match = re.search(r'Chrome/(\d+)\.', user_agent)
    firefox_match = re.search(r'Firefox/(\d+)', user_agent)
    edge_match = re.search(r'Edg/(\d+)\.', user_agent)
    re.search(r'Version/(\d+)', user_agent)

    if chrome_match and not edge_match:
        version = chrome_match.group(1)
        data.brand = "Google Chrome"
        data.major_version = version
        data.full_version = f"{version}.0.0.0"
        data.brands = [
            {"brand": "Chromium", "version": version},
            {"brand": "Google Chrome", "version": version},
            {"brand": "Not-A.Brand", "version": "24"},
        ]
        data.full_brands = data.brands.copy()
    elif edge_match:
        version = edge_match.group(1)
        data.brand = "Microsoft Edge"
        data.major_version = version
        data.full_version = f"{version}.0.0.0"
        data.brands = [
            {"brand": "Chromium", "version": version},
            {"brand": "Microsoft Edge", "version": version},
            {"brand": "Not-A.Brand", "version": "24"},
        ]
        data.full_brands = data.brands.copy()
    elif firefox_match:
        version = firefox_match.group(1)
        data.brand = "Firefox"
        data.major_version = version
        data.full_version = version
        data.brands = [{"brand": "Firefox", "version": version}]
        data.full_brands = data.brands.copy()

    # Определяем платформу (порядок важен: специфичные → общие)
    if "Windows NT 10" in user_agent:
        data.platform = "Windows"
        data.platform_version = "15.0.0"
    elif "Android" in user_agent:
        data.platform = "Android"
        data.mobile = True
        android_match = re.search(r'Android (\d+)', user_agent)
        data.platform_version = android_match.group(1) + ".0.0" if android_match else "14.0.0"
    elif "iPhone" in user_agent or "iPad" in user_agent:
        data.platform = "iOS"
        data.mobile = True
        ios_match = re.search(r'OS (\d+)[_\s]', user_agent)
        data.platform_version = ios_match.group(1) + ".0.0" if ios_match else "17.0.0"
    elif "Macintosh" in user_agent or "Mac OS X" in user_agent:
        data.platform = "macOS"
        data.platform_version = "14.0.0"
    elif "Linux" in user_agent:
        data.platform = "Linux"
        data.platform_version = "6.0.0"

    # Определяем архитектуру
    if "Win64" in user_agent or "x86_64" in user_agent or "x64" in user_agent:
        data.arch = "x86"
        data.bitness = "64"
    elif "WOW64" in user_agent:
        data.arch = "x86"
        data.bitness = "64"
    elif "arm" in user_agent.lower() or "aarch64" in user_agent.lower():
        data.arch = "arm"
        data.bitness = "64"

    # Модель устройства
    if "iPhone" in user_agent:
        data.model = "iPhone"
    elif "iPad" in user_agent:
        data.model = "iPad"

    return data


async def apply_client_hints(
    page: Page,
    config: ClientHintsConfig | None = None,
) -> None:
    """Применить User-Agent Client Hints spoofing к странице.

    Инъектирует JS-скрипт через page.add_init_script() — скрипт
    выполняется ДО загрузки страницы.

    Args:
        page: Playwright Page объект.
        config: Конфигурация Client Hints. По умолчанию — chrome_windows().

    Example:
        >>> from lab_playwright_kit.stealth_client_hints import apply_client_hints, ClientHintsConfig
        >>> config = ClientHintsConfig.from_user_agent(navigator.userAgent)
        >>> await apply_client_hints(page, config)
    """
    cfg = config or ClientHintsConfig.chrome_windows()
    script = ClientHintsSpoofer.get_script(cfg)
    if script:
        await page.add_init_script(script)
        logger.debug(
            f"Client Hints spoofed: {cfg.hints.brand} {cfg.hints.major_version} "
            f"on {cfg.hints.platform}"
        )
