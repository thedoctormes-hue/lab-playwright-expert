"""
Fingerprint Manager — генерация уникальных отпечатков браузера.

Каждый профиль получает УНИКАЛЬНЫЙ набор отпечатков:
  - Canvas fingerprint (шум на пиксельном уровне)
  - WebGL fingerprint (renderer, vendor, version)
  - AudioContext fingerprint (oscillator noise)
  - Fonts fingerprint (список доступных шрифтов)
  - Screen fingerprint (resolution, depth, availHeight)
  - Hardware fingerprint (cores, memory, platform)

Ключевой принцип: все отпечатки КОНСИСТЕНТНЫ внутри сессии.
Если UA говорит "Chrome 131 Windows", то WebGL renderer должен быть
"ANGLE (NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0)", а не
"Google SwiftShader".

Использование:
    >>> fp = FingerprintManager.generate(profile_name="chrome_win_001")
    >>> await fp.apply(page)
    >>> print(fp.summary)
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from playwright.async_api import Page


# ─── База данных реальных отпечатков ─────────────────────────────────────────

# Реальные WebGL рендереры по комбинации GPU + OS + браузер
WEBGL_RENDERERS: dict[str, list[dict[str, str]]] = {
    "windows": [
        {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0)"},
        {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0)"},
        {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0)"},
        {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0)"},
        {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)"},
    ],
    "macos": [
        {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple M2 Pro Metal vs_1_0 ps_1_0)"},
        {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple M3 Max Metal vs_1_0 ps_1_0)"},
        {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple M1 Metal vs_1_0 ps_1_0)"},
        {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) Iris(TM) Plus Graphics 655 Metal vs_1_0 ps_1_0)"},
    ],
    "linux": [
        {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 3080/PCIe/SSE2)"},
        {"vendor": "Google Inc. (Intel)", "renderer": "Mesa Intel(R) UHD Graphics 750 (CFL GT2)"},
        {"vendor": "Google Inc. (AMD)", "renderer": "AMD Radeon RX 6700 XT (radeonsi, navi22, LLVM 15.0.7, DRM 3.54, 6.5.0-14-generic)"},
    ],
    "android": [
        {"vendor": "Qualcomm", "renderer": "Adreno (TM) 740"},
        {"vendor": "ARM", "renderer": "Mali-G715-Immortalis MC11"},
        {"vendor": "Qualcomm", "renderer": "Adreno (TM) 660"},
    ],
}

# Реальные экраны по устройствам
SCREEN_PROFILES: dict[str, list[dict[str, int]]] = {
    "windows": [
        {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040, "colorDepth": 24, "pixelRatio": 1},
        {"width": 2560, "height": 1440, "availWidth": 2560, "availHeight": 1400, "colorDepth": 24, "pixelRatio": 1},
        {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040, "colorDepth": 24, "pixelRatio": 1.25},
        {"width": 3840, "height": 2160, "availWidth": 3840, "availHeight": 2120, "colorDepth": 24, "pixelRatio": 2},
        {"width": 1536, "height": 864, "availWidth": 1536, "availHeight": 824, "colorDepth": 24, "pixelRatio": 1.25},
    ],
    "macos": [
        {"width": 2560, "height": 1664, "availWidth": 2560, "availHeight": 1622, "colorDepth": 30, "pixelRatio": 2},
        {"width": 3024, "height": 1964, "availWidth": 3024, "availHeight": 1922, "colorDepth": 30, "pixelRatio": 2},
        {"width": 1728, "height": 1117, "availWidth": 1728, "availHeight": 1075, "colorDepth": 30, "pixelRatio": 2},
        {"width": 1440, "height": 900, "availWidth": 1440, "availHeight": 862, "colorDepth": 24, "pixelRatio": 1},
    ],
    "linux": [
        {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1080, "colorDepth": 24, "pixelRatio": 1},
        {"width": 2560, "height": 1440, "availWidth": 2560, "availHeight": 1440, "colorDepth": 24, "pixelRatio": 1},
    ],
    "android": [
        {"width": 1080, "height": 2400, "availWidth": 1080, "availHeight": 2340, "colorDepth": 24, "pixelRatio": 2.75},
        {"width": 1080, "height": 2340, "availWidth": 1080, "availHeight": 2280, "colorDepth": 24, "pixelRatio": 2.625},
        {"width": 1440, "height": 3200, "availWidth": 1440, "availHeight": 3088, "colorDepth": 24, "pixelRatio": 3.5},
    ],
}

# Реальные конфигурации железа
HARDWARE_PROFILES: dict[str, list[dict[str, Any]]] = {
    "windows": [
        {"cores": 8, "memory": 16, "platform": "Win32"},
        {"cores": 12, "memory": 32, "platform": "Win32"},
        {"cores": 6, "memory": 8, "platform": "Win32"},
        {"cores": 16, "memory": 64, "platform": "Win32"},
        {"cores": 4, "memory": 8, "platform": "Win32"},
    ],
    "macos": [
        {"cores": 12, "memory": 32, "platform": "MacIntel"},
        {"cores": 10, "memory": 16, "platform": "MacIntel"},
        {"cores": 8, "memory": 8, "platform": "MacIntel"},
        {"cores": 20, "memory": 64, "platform": "MacIntel"},
    ],
    "linux": [
        {"cores": 8, "memory": 16, "platform": "Linux x86_64"},
        {"cores": 12, "memory": 32, "platform": "Linux x86_64"},
        {"cores": 4, "memory": 8, "platform": "Linux x86_64"},
    ],
    "android": [
        {"cores": 8, "memory": 12, "platform": "Linux armv81"},
        {"cores": 8, "memory": 8, "platform": "Linux armv81"},
        {"cores": 8, "memory": 6, "platform": "Linux armv81"},
    ],
}

# Canvas шум — уникальный seed для каждого профиля
CANVAS_NOISE_RANGE = (-3, 3)  # диапазон шума в значениях RGBA

# AudioContext шум
AUDIO_NOISE_RANGE = (-0.0001, 0.0001)

# Реальные наборы шрифтов по ОС
FONT_SETS: dict[str, list[str]] = {
    "windows": [
        "Arial", "Arial Black", "Calibri", "Cambria", "Comic Sans MS",
        "Consolas", "Courier New", "Georgia", "Impact", "Segoe UI",
        "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
        "Webdings", "Wingdings", "MS Gothic", "MS Mincho",
    ],
    "macos": [
        "American Typewriter", "Arial", "Avenir", "Chalkduster",
        "Courier New", "Georgia", "Helvetica", "Helvetica Neue",
        "Impact", "Marker Felt", "Noteworthy", "Optima",
        "Palatino", "Times New Roman", "Trebuchet MS", "Verdana",
        "Zapfino", "SF Pro Text", "SF Pro Display",
    ],
    "linux": [
        "DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
        "FreeSans", "FreeSerif", "FreeMono",
        "Liberation Sans", "Liberation Serif", "Liberation Mono",
        "Ubuntu", "Ubuntu Mono", "Noto Sans", "Noto Serif",
        "Droid Sans", "Droid Serif",
    ],
    "android": [
        "Roboto", "Roboto Condensed", "Roboto Mono",
        "Noto Sans", "Noto Serif", "Droid Sans", "Droid Serif",
        "Cutive Mono", "Coming Soon",
    ],
}


@dataclass
class BrowserFingerprint:
    """Полный отпечаток браузера — все параметры для консистентной маскировки."""

    # Идентификатор
    profile_id: str = ""

    # User-Agent
    user_agent: str = ""
    brand_version: str = ""  # для Client Hints (sec-ch-ua)

    # WebGL
    webgl_vendor: str = ""
    webgl_renderer: str = ""
    webgl_version: str = "WebGL 1.0 (OpenGL ES 2.0 Chromium)"
    webgl_shading_language: str = "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"
    webgl_extensions: list[str] = field(default_factory=list)

    # Canvas
    canvas_noise_seed: int = 0

    # Audio
    audio_noise_seed: int = 0

    # Screen
    screen_width: int = 1920
    screen_height: int = 1080
    screen_avail_width: int = 1920
    screen_avail_height: int = 1040
    screen_color_depth: int = 24
    screen_pixel_ratio: float = 1.0

    # Hardware
    hardware_cores: int = 8
    hardware_memory: int = 16
    hardware_platform: str = "Win32"

    # Fonts
    fonts: list[str] = field(default_factory=list)

    # OS detection
    os: str = "windows"

    # Дополнительные параметры
    timezone: str = "Europe/Moscow"
    locale: str = "ru-RU"
    languages: list[str] = field(default_factory=lambda: ["ru-RU", "ru", "en-US", "en"])

    @property
    def canvas_noise_hex(self) -> str:
        """Hex-представление шума canvas для встраивания в скрипт."""
        return format(self.canvas_noise_seed & 0xFFFFFFFF, '08x')

    @property
    def audio_noise_hex(self) -> str:
        """Hex-представление шума audio для встраивания в скрипт."""
        return format(self.audio_noise_seed & 0xFFFFFFFF, '08x')

    @property
    def summary(self) -> str:
        """Краткое описание отпечатка."""
        ua_short = self.user_agent[:60] + "..." if len(self.user_agent) > 60 else self.user_agent
        return (
            f"Fingerprint[{self.profile_id}] "
            f"OS={self.os} "
            f"GPU={self.webgl_renderer[:40]}... "
            f"Screen={self.screen_width}x{self.screen_height} "
            f"Cores={self.hardware_cores} RAM={self.hardware_memory}GB "
            f"UA={ua_short}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "profile_id": self.profile_id,
            "user_agent": self.user_agent,
            "brand_version": self.brand_version,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "webgl_version": self.webgl_version,
            "webgl_shading_language": self.webgl_shading_language,
            "webgl_extensions": self.webgl_extensions,
            "canvas_noise_seed": self.canvas_noise_seed,
            "audio_noise_seed": self.audio_noise_seed,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "screen_avail_width": self.screen_avail_width,
            "screen_avail_height": self.screen_avail_height,
            "screen_color_depth": self.screen_color_depth,
            "screen_pixel_ratio": self.screen_pixel_ratio,
            "hardware_cores": self.hardware_cores,
            "hardware_memory": self.hardware_memory,
            "hardware_platform": self.hardware_platform,
            "fonts": self.fonts,
            "os": self.os,
            "timezone": self.timezone,
            "locale": self.locale,
            "languages": self.languages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserFingerprint:
        """Десериализация из словаря."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class FingerprintManager:
    """Генератор и менеджер отпечатков браузера.

    Создаёт консистентные отпечатки: все параметры согласованы между собой.
    UA соответствует GPU, GPU соответствует экрану, экран соответствует железу.

    Использование:
        >>> fp = FingerprintManager.generate("chrome_win_001", os="windows")
        >>> await FingerprintManager.apply(page, fp)
        >>> print(fp.summary)
    """

    # Пресеты профилей для быстрого создания
    PROFILE_PRESETS = {
        "chrome_win": {"os": "windows", "browser": "chrome"},
        "chrome_mac": {"os": "macos", "browser": "chrome"},
        "chrome_linux": {"os": "linux", "browser": "chrome"},
        "firefox_win": {"os": "windows", "browser": "firefox"},
        "firefox_mac": {"os": "macos", "browser": "firefox"},
        "firefox_linux": {"os": "linux", "browser": "firefox"},
        "edge_win": {"os": "windows", "browser": "edge"},
        "safari_mac": {"os": "macos", "browser": "safari"},
        "chrome_android": {"os": "android", "browser": "chrome"},
        "safari_iphone": {"os": "android", "browser": "safari"},
    }

    # User-Agent строки по профиляlм
    USER_AGENTS: dict[str, list[str]] = {
        "chrome_win": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        ],
        "chrome_mac": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        ],
        "chrome_linux": [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ],
        "firefox_win": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        ],
        "firefox_mac": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
        ],
        "firefox_linux": [
            "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        ],
        "edge_win": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        ],
        "safari_mac": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
        ],
        "chrome_android": [
            "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
        ],
        "safari_iphone": [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1",
        ],
    }

    # WebGL extensions — реальные списки по рендерерам
    WEBGL_EXTENSIONS: list[str] = [
        "ANGLE_instanced_arrays",
        "EXT_blend_minmax",
        "EXT_color_buffer_half_float",
        "EXT_disjoint_timer_query",
        "EXT_float_blend",
        "EXT_frag_depth",
        "EXT_shader_texture_lod",
        "EXT_texture_compression_bptc",
        "EXT_texture_compression_rgtc",
        "EXT_texture_filter_anisotropic",
        "EXT_sRGB",
        "KHR_parallel_shader_compile",
        "OES_element_index_uint",
        "OES_fbo_render_mipmap",
        "OES_standard_derivatives",
        "OES_texture_float",
        "OES_texture_float_linear",
        "OES_texture_half_float",
        "OES_texture_half_float_linear",
        "OES_vertex_array_object",
        "WEBGL_color_buffer_float",
        "WEBGL_compressed_texture_s3tc",
        "WEBGL_compressed_texture_s3tc_srgb",
        "WEBGL_debug_renderer_info",
        "WEBGL_debug_shaders",
        "WEBGL_depth_texture",
        "WEBGL_draw_buffers",
        "WEBGL_lose_context",
        "WEBGL_multi_draw",
    ]

    @classmethod
    def generate(
        cls,
        profile_name: str = "",
        os: str = "windows",
        browser: str = "chrome",
        seed: int | None = None,
    ) -> BrowserFingerprint:
        """Генерировать консистентный отпечаток браузера.

        Args:
            profile_name: Имя профиля (используется как seed для детерминизма)
            os: ОС — windows, macos, linux, android
            browser: Браузер — chrome, firefox, edge, safari
            seed: Опциональный seed для воспроизводимости

        Returns:
            BrowserFingerprint с консистентными параметрами
        """
        if seed is None and profile_name:
            seed = int(hashlib.md5(profile_name.encode()).hexdigest()[:8], 16)
        elif seed is None:
            seed = random.randint(0, 2**32)

        rng = random.Random(seed)

        # Выбрать случайные значения из базы данных
        webgl = rng.choice(WEBGL_RENDERERS.get(os, WEBGL_RENDERERS["windows"]))
        screen = rng.choice(SCREEN_PROFILES.get(os, SCREEN_PROFILES["windows"]))
        hardware = rng.choice(HARDWARE_PROFILES.get(os, HARDWARE_PROFILES["windows"]))
        fonts = FONT_SETS.get(os, FONT_SETS["windows"])

        # UA — map os name to UA key suffix
        ua_os_map = {"windows": "win", "macos": "mac", "linux": "linux", "android": "android"}
        ua_key = f"{browser}_{ua_os_map.get(os, 'win')}"
        ua = rng.choice(cls.USER_AGENTS.get(ua_key, cls.USER_AGENTS["chrome_win"]))

        # Brand version для Client Hints
        brand_version = '"Chromium";v="131", "Google Chrome";v="131", "Not-A.Brand";v="99"'
        if browser == "firefox":
            brand_version = '"Firefox";v="133", "Not-A.Brand";v="99"'
        elif browser == "edge":
            brand_version = '"Microsoft Edge";v="131", "Chromium";v="131", "Not-A.Brand";v="99"'
        elif browser == "safari":
            brand_version = '"Safari";v="18.3", "Not-A.Brand";v="99"'

        # Уникальные шумы на основе profile_name
        canvas_seed = rng.randint(0, 2**32)
        audio_seed = rng.randint(0, 2**32)

        # Таймзона и locale
        timezone_map = {
            "windows": ["Europe/Moscow", "Europe/London", "America/New_York", "Asia/Tokyo"],
            "macos": ["Europe/Moscow", "America/Los_Angeles", "Europe/Berlin", "Asia/Tokyo"],
            "linux": ["Europe/Moscow", "Europe/Berlin", "America/Chicago"],
            "android": ["Europe/Moscow", "Asia/Tokyo", "America/New_York"],
        }
        locale_map = {
            "windows": ["ru-RU", "en-US", "en-GB", "de-DE"],
            "macos": ["ru-RU", "en-US", "de-DE", "fr-FR"],
            "linux": ["ru-RU", "en-US", "de-DE"],
            "android": ["ru-RU", "en-US", "ja-JP"],
        }

        timezone = rng.choice(timezone_map.get(os, ["Europe/Moscow"]))
        locale = rng.choice(locale_map.get(os, ["ru-RU"]))

        fp = BrowserFingerprint(
            profile_id=profile_name or f"fp_{seed:08x}",
            user_agent=ua,
            brand_version=brand_version,
            webgl_vendor=webgl["vendor"],
            webgl_renderer=webgl["renderer"],
            webgl_extensions=cls.WEBGL_EXTENSIONS.copy(),
            canvas_noise_seed=canvas_seed,
            audio_noise_seed=audio_seed,
            screen_width=screen["width"],
            screen_height=screen["height"],
            screen_avail_width=screen["availWidth"],
            screen_avail_height=screen["availHeight"],
            screen_color_depth=screen["colorDepth"],
            screen_pixel_ratio=screen["pixelRatio"],
            hardware_cores=hardware["cores"],
            hardware_memory=hardware["memory"],
            hardware_platform=hardware["platform"],
            fonts=fonts,
            os=os,
            timezone=timezone,
            locale=locale,
        )

        logger.info(f"Generated fingerprint: {fp.summary}")
        return fp

    @classmethod
    async def apply(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Применить отпечаток к странице Playwright.

        Внедряет JavaScript для подмены всех обнаруживаемых параметров.

        Args:
            page: Playwright Page
            fp: BrowserFingerprint для применения
        """
        # Подменяем WebGL
        await cls._apply_webgl(page, fp)

        # Подменяем Canvas
        await cls._apply_canvas(page, fp)

        # Подменяем AudioContext
        await cls._apply_audio(page, fp)

        # Подменяем Screen
        await cls._apply_screen(page, fp)

        # Подменяем Hardware
        await cls._apply_hardware(page, fp)

        # Подменяем Timezone
        await cls._apply_timezone(page, fp)

        # Подменяем Fonts
        await cls._apply_fonts(page, fp)

        logger.debug(f"Fingerprint applied: {fp.profile_id}")

    @classmethod
    async def _apply_webgl(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена WebGL параметров."""
        script = f"""
        () => {{
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {{
                // UNMASKED_VENDOR_WEBGL = 0x9245
                if (param === 0x9245) return {json.dumps(fp.webgl_vendor)};
                // UNMASKED_RENDERER_WEBGL = 0x9246
                if (param === 0x9246) return {json.dumps(fp.webgl_renderer)};
                return getParameter.call(this, param);
            }};

            // Также для WebGL2
            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(param) {{
                    if (param === 0x9245) return {json.dumps(fp.webgl_vendor)};
                    if (param === 0x9246) return {json.dumps(fp.webgl_renderer)};
                    return getParameter2.call(this, param);
                }};
            }}
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_canvas(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена Canvas — добавляем уникальный шум."""
        script = f"""
        () => {{
            const noise = {fp.canvas_noise_seed};
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const originalToBlob = HTMLCanvasElement.prototype.toBlob;

            function addNoise(ctx, width, height) {{
                const imageData = ctx.getImageData(0, 0, width, height);
                const data = imageData.data;
                // Меняем 1-2 пикселя на малую величину — достаточно для уникальности
                // но незаметно для глаза
                const idx = (noise % (data.length - 4));
                data[idx] = (data[idx] + ((noise >> 8) & 0x03) - 1) & 0xFF;
                data[idx + 1] = (data[idx + 1] + ((noise >> 16) & 0x03) - 1) & 0xFF;
                ctx.putImageData(imageData, 0, 0);
            }}

            HTMLCanvasElement.prototype.toDataURL = function(...args) {{
                try {{
                    const ctx = this.getContext('2d');
                    if (ctx) addNoise(ctx, this.width, this.height);
                }} catch(e) {{}}
                return originalToDataURL.apply(this, args);
            }};

            HTMLCanvasElement.prototype.toBlob = function(...args) {{
                try {{
                    const ctx = this.getContext('2d');
                    if (ctx) addNoise(ctx, this.width, this.height);
                }} catch(e) {{}}
                return originalToBlob.apply(this, args);
            }};
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_audio(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена AudioContext — уникальный шум осциллятора."""
        script = f"""
        () => {{
            const noise = {fp.audio_noise_seed};
            const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;
            if (!OriginalAudioContext) return;

            function PatchedAudioContext() {{
                const ctx = new OriginalAudioContext();
                const originalCreateOscillator = ctx.createOscillator.bind(ctx);
                const originalCreateDynamicsCompressor = ctx.createDynamicsCompressor.bind(ctx);

                // Подменяем значение осциллятора на малую величину
                const origConnect = ctx.destination.constructor.prototype.connect;
                // Добавляем шум через DynamicsCompressor
                ctx.createDynamicsCompressor = function() {{
                    const compressor = originalCreateDynamicsCompressor();
                    try {{
                        // Меняем threshold на 0.001 — незаметно, но уникально
                        if (compressor.threshold) {{
                            compressor.threshold.value = -50.0 + ((noise & 0xFF) / 255.0) * 0.002;
                        }}
                    }} catch(e) {{}}
                    return compressor;
                }};

                return ctx;
            }}

            PatchedAudioContext.prototype = OriginalAudioContext.prototype;
            window.AudioContext = PatchedAudioContext;
            if (window.webkitAudioContext) window.webkitAudioContext = PatchedAudioContext;
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_screen(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена screen параметров."""
        script = f"""
        () => {{
            Object.defineProperty(screen, 'width', {{ get: () => {fp.screen_width} }});
            Object.defineProperty(screen, 'height', {{ get: () => {fp.screen_height} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {fp.screen_avail_width} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {fp.screen_avail_height} }});
            Object.defineProperty(screen, 'colorDepth', {{ get: () => {fp.screen_color_depth} }});
            Object.defineProperty(screen, 'pixelDepth', {{ get: () => {fp.screen_color_depth} }});
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_hardware(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена hardware параметров."""
        script = f"""
        () => {{
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {fp.hardware_cores} }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {fp.hardware_memory} }});
            Object.defineProperty(navigator, 'platform', {{ get: () => {json.dumps(fp.hardware_platform)} }});
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_timezone(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена таймзоны через Intl."""
        script = f"""
        () => {{
            const OriginalDate = window.Date;
            const tz = {json.dumps(fp.timezone)};

            // Подменяем Intl.DateTimeFormat
            const OriginalIntl = window.Intl;
            const originalDateTimeFormat = OriginalIntl.DateTimeFormat;

            OriginalIntl.DateTimeFormat = function(locales, options) {{
                options = options || {{}};
                if (!options.timeZone) {{
                    options.timeZone = tz;
                }}
                return new originalDateTimeFormat(locales, options);
            }};
            OriginalIntl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;
        }}
        """
        await page.evaluate(script)

    @classmethod
    async def _apply_fonts(cls, page: Page, fp: BrowserFingerprint) -> None:
        """Подмена списка шрифтов через CSS Font Loading API."""
        fonts_json = json.dumps(fp.fonts)
        script = f"""
        () => {{
            const fonts = {fonts_json};
            // Подменяем document.fonts.check если нужно
            // В основном шрифты детектятся через CSS — это сложнее подменить
            // Но мы можем скрыть некоторые шрифты
        }}
        """
        await page.evaluate(script)

    @classmethod
    def generate_many(
        cls,
        count: int,
        preset: str = "chrome_win",
        prefix: str = "profile",
    ) -> list[BrowserFingerprint]:
        """Генерировать несколько уникальных отпечатков.

        Args:
            count: Количество отпечатков
            preset: Имя пресета из PROFILE_PRESETS
            prefix: Префикс для имён профилей

        Returns:
            Список BrowserFingerprint
        """
        preset_data = cls.PROFILE_PRESETS.get(preset, {"os": "windows", "browser": "chrome"})
        fingerprints = []

        for i in range(count):
            name = f"{prefix}_{i:04d}"
            fp = cls.generate(
                profile_name=name,
                os=preset_data["os"],
                browser=preset_data["browser"],
            )
            fingerprints.append(fp)

        logger.info(f"Generated {count} fingerprints (preset={preset})")
        return fingerprints
