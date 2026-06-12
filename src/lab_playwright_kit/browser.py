"""
Управление браузером: контекст, профили, сессии.

Поддерживает два движка:
  - playwright: стандартный Playwright + StealthPipeline (по умолчанию)
  - cloakbrowser: модифицированный Chromium с C++ патчами (для обхода антибота)

При использовании cloakbrowser StealthPipeline НЕ применяется —
маскировка уже встроена в бинарник на уровне исходного кода C++.

Поддерживает автоматическое применение StealthPipeline при создании страниц
(только для playwright engine).
"""
from __future__ import annotations

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

# Путь к бинарнику CloakBrowser
CLOAKBROWSER_PATH = "/root/.cloakbrowser/chromium-146.0.7680.177.3/chrome"


class BrowserManager:
    """Асинхронный менеджер браузера Playwright / CloakBrowser."""

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        user_agent: str | None = None,
        proxy: dict | None = None,
        profile_dir: str | None = None,
        timeout: int = 30000,
        viewport: dict | None = None,
        stealth: "StealthPipeline | str | None" = None,
        engine: str = "playwright",
        humanize: bool = False,
        cloak_platform: str = "windows",
        cloak_fingerprint_seed: int | None = None,
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.user_agent = user_agent
        self.proxy = proxy
        self.profile_dir = profile_dir
        self.timeout = timeout
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self.engine = engine
        self.humanize = humanize
        self.cloak_platform = cloak_platform
        self.cloak_fingerprint_seed = cloak_fingerprint_seed

        # StealthPipeline: можно передать объект, строку уровня, или None
        # НЕ применяется при engine="cloakbrowser"
        if stealth is not None and engine != "cloakbrowser":
            from lab_playwright_kit.stealth_pipeline import StealthPipeline as _SP
            if isinstance(stealth, _SP):
                self._stealth = stealth
            elif isinstance(stealth, str):
                self._stealth = _SP.level(stealth)
            else:
                self._stealth = None
        else:
            self._stealth = None

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._closed: bool = False

    async def __aenter__(self) -> BrowserManager:
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    async def start(self) -> None:
        """Запустить браузер."""
        if self.engine == "cloakbrowser":
            await self._start_cloakbrowser()
        else:
            await self._start_playwright()

    async def _start_playwright(self) -> None:
        """Запустить стандартный Playwright Chromium."""
        self._playwright = await async_playwright().start()

        launcher = getattr(self._playwright, self.browser_type)
        launch_kwargs: dict = {
            "headless": self.headless,
        }

        if self.profile_dir:
            self._context = await launcher.launch_persistent_context(
                user_data_dir=self.profile_dir,
                viewport=self.viewport,
                user_agent=self.user_agent,
                proxy=self.proxy,
                **launch_kwargs,
            )
            self._browser = self._context.browser
        else:
            self._browser = await launcher.launch(**launch_kwargs)
            self._context = await self._browser.new_context(
                viewport=self.viewport,
                user_agent=self.user_agent,
                proxy=self.proxy,
            )

        self._context.set_default_timeout(self.timeout)
        logger.info(f"Browser started: playwright/{self.browser_type}, headless={self.headless}")

    async def _start_cloakbrowser(self) -> None:
        """Запустить CloakBrowser (модифицированный Chromium с C++ патчами).

        StealthPipeline НЕ применяется — маскировка встроена в бинарник.
        Поддерживает persistent context через profile_dir.
        """
        from cloakbrowser import launch_async, launch_persistent_context_async, get_default_stealth_args

        # Формируем stealth-аргументы
        stealth_args = get_default_stealth_args() if self.cloak_fingerprint_seed is None else [
            f"--fingerprint={self.cloak_fingerprint_seed}",
            f"--fingerprint-platform={self.cloak_platform}",
        ]

        # Добавляем прокси если указан
        proxy_str = None
        if self.proxy:
            if isinstance(self.proxy, dict):
                server = self.proxy.get("server", "")
                username = self.proxy.get("username", "")
                password = self.proxy.get("password", "")
                if username and password:
                    proxy_str = f"{username}:{password}@{server}"
                else:
                    proxy_str = server
            else:
                proxy_str = str(self.proxy)

        launch_kwargs: dict = {
            "headless": self.headless,
            "stealth_args": stealth_args,
            "humanize": self.humanize,
        }
        if proxy_str:
            launch_kwargs["proxy"] = proxy_str

        if self.profile_dir:
            # Persistent context — cookies, localStorage, кэш сохраняются
            self._context = await launch_persistent_context_async(
                self.profile_dir,
                viewport=self.viewport,
                user_agent=self.user_agent,
                **launch_kwargs,
            )
            self._browser = self._context.browser
        else:
            self._browser = await launch_async(**launch_kwargs)
            self._context = await self._browser.new_context(
                viewport=self.viewport,
                user_agent=self.user_agent,
            )

        self._context.set_default_timeout(self.timeout)
        logger.info(
            f"Browser started: cloakbrowser, headless={self.headless}, "
            f"humanize={self.humanize}, platform={self.cloak_platform}"
        )

    async def stop(self) -> None:
        """Остановить браузер. Идемпотентный — безопасен для многократного вызова."""
        if self._closed:
            return
        self._closed = True
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        # playwright.stop() только для стандартного Playwright engine
        # CloakBrowser управляет процессом самостоятельно
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        logger.info(f"Browser stopped (engine={self.engine})")

    async def new_page(self, apply_stealth: bool = True) -> Page:
        """Создать новую страницу.

        Args:
            apply_stealth: Применить StealthPipeline если настроен.
                Игнорируется при engine="cloakbrowser" (маскировка встроена).
        """
        page = await self._context.new_page()
        # StealthPipeline только для playwright engine
        if self.engine != "cloakbrowser" and apply_stealth and self._stealth is not None:
            await self._stealth.apply(page)
        return page

    async def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        apply_stealth: bool = True,
    ) -> Page:
        """Открыть URL и вернуть страницу.

        Args:
            url: URL для навигации.
            wait_until: Условие ожидания.
            apply_stealth: Применить StealthPipeline если настроен.
        """
        page = await self.new_page(apply_stealth=apply_stealth)
        await page.goto(url, wait_until=wait_until)
        logger.debug(f"Navigated to {url}")
        return page

    @property
    def context(self) -> BrowserContext:
        if not self._context:
            raise RuntimeError("Browser not started")
        return self._context

    @property
    def browser(self) -> Browser:
        if not self._browser:
            raise RuntimeError("Browser not started")
        return self._browser
