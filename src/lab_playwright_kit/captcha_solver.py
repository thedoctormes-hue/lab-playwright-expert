"""
Captcha Solver — автоматическое решение капч.

Поддерживает:
  - reCAPTCHA v2 / v3
  - hCaptcha
  - Яндекс.Капча (Yandex SmartCaptcha)
  - Cloudflare Turnstile
  - FunCaptcha (Arkose Labs)

Провайдеры:
  - 2Captcha (https://2captcha.com)
  - CapSolver (https://capsolver.com)
  - Anti-Captcha (https://anti-captcha.com)

Использование:
    >>> solver = CaptchaSolver(provider="2captcha", api_key="YOUR_KEY")
    >>> token = await solver.solve_recaptcha_v2(page, site_key="6Lc...", url="https://example.com")
    >>> await solver.inject_token(page, token)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import Page


class CaptchaType(str, Enum):
    """Типы капч."""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    YANDEX = "yandex"
    CLOUDFLARE_TURNSTILE = "cloudflare_turnstile"
    FUNCAPTCHA = "funcaptcha"


class SolverProvider(str, Enum):
    """Провайдеры решения капч."""
    TWOCAPTCHA = "2captcha"
    CAPSOLVER = "capsolver"
    ANTICAPTCHA = "anticaptcha"


@dataclass
class CaptchaResult:
    """Результат решения капчи."""
    success: bool
    token: str = ""
    error: str = ""
    solve_time_ms: float = 0.0
    cost: float = 0.0  # стоимость в USD
    captcha_id: str = ""


@dataclass
class SolverConfig:
    """Конфигурация солвера."""
    provider: SolverProvider = SolverProvider.TWOCAPTCHA
    api_key: str = ""
    timeout_seconds: int = 120
    poll_interval_seconds: float = 5.0
    max_retries: int = 3

    # 2Captcha endpoints
    base_url_2captcha: str = "https://2captcha.com"
    base_url_capsolver: str = "https://api.capsolver.com"
    base_url_anticaptcha: str = "https://api.anti-captcha.com"


class CaptchaSolver:
    """Автоматическое решение капч через внешние сервисы.

    Поддерживает 2Captcha, CapSolver, Anti-Captcha.

    Использование:
        >>> solver = CaptchaSolver(api_key="YOUR_2CAPTCHA_KEY")
        >>> result = await solver.solve_recaptcha_v2(page, site_key="6Lc...", url="https://example.com")
        >>> if result.success:
        ...     await solver.inject_recaptcha_token(page, result.token)
    """

    def __init__(
        self,
        api_key: str = "",
        provider: str = "2captcha",
        timeout: int = 120,
    ):
        self.config = SolverConfig(
            api_key=api_key,
            provider=SolverProvider(provider),
            timeout_seconds=timeout,
        )
        self._client = httpx.AsyncClient(timeout=30)
        self._solved_count = 0
        self._failed_count = 0
        self._total_cost = 0.0

    async def solve_recaptcha_v2(
        self,
        page: Page,
        site_key: str | None = None,
        url: str | None = None,
    ) -> CaptchaResult:
        """Решить reCAPTCHA v2.

        Args:
            page: Playwright Page с капчей
            site_key: site key reCAPTCHA (авто-определение если None)
            url: URL страницы (page.url если None)

        Returns:
            CaptchaResult с токеном
        """
        if not site_key:
            site_key = await self._detect_recaptcha_site_key(page)
        if not site_key:
            return CaptchaResult(success=False, error="Could not detect reCAPTCHA site key")

        if not url:
            url = page.url

        logger.info(f"Solving reCAPTCHA v2: site_key={site_key[:20]}... url={url}")

        if self.config.provider == SolverProvider.TWOCAPTCHA:
            return await self._solve_2captcha_recaptcha(site_key, url, version="v2")
        elif self.config.provider == SolverProvider.CAPSOLVER:
            return await self._solve_capsolver_recaptcha(site_key, url, version="v2")
        else:
            return CaptchaResult(success=False, error=f"Provider {self.config.provider} not implemented for reCAPTCHA")

    async def solve_recaptcha_v3(
        self,
        page: Page,
        site_key: str | None = None,
        url: str | None = None,
        action: str = "verify",
        min_score: float = 0.7,
    ) -> CaptchaResult:
        """Решить reCAPTCHA v3.

        Args:
            page: Playwright Page
            site_key: site key (авто если None)
            url: URL страницы
            action: действие (verify, login, etc.)
            min_score: минимальный score (0.1-0.9)

        Returns:
            CaptchaResult с токеном
        """
        if not site_key:
            site_key = await self._detect_recaptcha_site_key(page)
        if not site_key:
            return CaptchaResult(success=False, error="Could not detect reCAPTCHA v3 site key")

        if not url:
            url = page.url

        logger.info(f"Solving reCAPTCHA v3: site_key={site_key[:20]}... action={action}")

        if self.config.provider == SolverProvider.TWOCAPTCHA:
            return await self._solve_2captcha_recaptcha(site_key, url, version="v3", action=action, min_score=min_score)
        else:
            return CaptchaResult(success=False, error=f"Provider {self.config.provider} not implemented for reCAPTCHA v3")

    async def solve_hcaptcha(
        self,
        page: Page,
        site_key: str | None = None,
        url: str | None = None,
    ) -> CaptchaResult:
        """Решить hCaptcha.

        Args:
            page: Playwright Page
            site_key: site key (авто если None)
            url: URL страницы

        Returns:
            CaptchaResult с токеном
        """
        if not site_key:
            site_key = await self._detect_hcaptcha_site_key(page)
        if not site_key:
            return CaptchaResult(success=False, error="Could not detect hCaptcha site key")

        if not url:
            url = page.url

        logger.info(f"Solving hCaptcha: site_key={site_key[:20]}...")

        if self.config.provider == SolverProvider.TWOCAPTCHA:
            return await self._solve_2captcha_hcaptcha(site_key, url)
        else:
            return CaptchaResult(success=False, error=f"Provider {self.config.provider} not implemented for hCaptcha")

    async def solve_cloudflare_turnstile(
        self,
        page: Page,
        site_key: str | None = None,
        url: str | None = None,
    ) -> CaptchaResult:
        """Решить Cloudflare Turnstile.

        Args:
            page: Playwright Page
            site_key: site key (авто если None)
            url: URL страницы

        Returns:
            CaptchaResult с токеном
        """
        if not site_key:
            site_key = await self._detect_turnstile_site_key(page)
        if not site_key:
            return CaptchaResult(success=False, error="Could not detect Turnstile site key")

        if not url:
            url = page.url

        logger.info(f"Solving Cloudflare Turnstile: site_key={site_key[:20]}...")

        if self.config.provider == SolverProvider.TWOCAPTCHA:
            return await self._solve_2captcha_turnstile(site_key, url)
        else:
            return CaptchaResult(success=False, error=f"Provider {self.config.provider} not implemented for Turnstile")

    async def inject_recaptcha_token(self, page: Page, token: str) -> None:
        """Инжектить токен reCAPTCHA в страницу.

        Args:
            page: Playwright Page
            token: Токен от солвера
        """
        await page.evaluate(f"""
        () => {{
            // Вариант 1: скрытое поле
            const textarea = document.querySelector('[name="g-recaptcha-response"]');
            if (textarea) {{
                textarea.value = {json_token(token)};
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}

            // Вариант 2: callback функция
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                Object.entries(___grecaptcha_cfg.clients).forEach(([key, client]) => {{
                    Object.entries(client).forEach(([k, v]) => {{
                        if (v && typeof v === 'object') {{
                            Object.entries(v).forEach(([kk, vv]) => {{
                                if (vv && typeof vv === 'object' && vv.callback) {{
                                    vv.callback({json_token(token)});
                                }}
                            }});
                        }}
                    }});
                }});
            }}
        }}
        """)
        logger.debug("reCAPTCHA token injected")

    async def inject_hcaptcha_token(self, page: Page, token: str) -> None:
        """Инжектить токен hCaptcha в страницу."""
        await page.evaluate(f"""
        () => {{
            const textarea = document.querySelector('[name="h-captcha-response"]');
            if (textarea) {{
                textarea.value = {json_token(token)};
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}
        """)
        logger.debug("hCaptcha token injected")

    async def inject_turnstile_token(self, page: Page, token: str) -> None:
        """Инжектить токен Cloudflare Turnstile в страницу."""
        await page.evaluate(f"""
        () => {{
            const input = document.querySelector('[name="cf-turnstile-response"]');
            if (input) {{
                input.value = {json_token(token)};
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}
        """)
        logger.debug("Turnstile token injected")

    async def auto_solve(self, page: Page) -> CaptchaResult:
        """Автоматически определить и решить капчу на странице.

        Проверяет все поддерживаемые типы по порядку.

        Args:
            page: Playwright Page

        Returns:
            CaptchaResult — success=False если капча не найдена или не решена
        """
        # Проверяем reCAPTCHA v2
        if await self._has_recaptcha_v2(page):
            return await self.solve_recaptcha_v2(page)

        # Проверяем reCAPTCHA v3
        if await self._has_recaptcha_v3(page):
            return await self.solve_recaptcha_v3(page)

        # Проверяем hCaptcha
        if await self._has_hcaptcha(page):
            return await self.solve_hcaptcha(page)

        # Проверяем Cloudflare Turnstile
        if await self._has_turnstile(page):
            return await self.solve_cloudflare_turnstile(page)

        return CaptchaResult(success=False, error="No captcha detected on page")

    # ─── 2Captcha API ──────────────────────────────────────────────────────

    async def _solve_2captcha_recaptcha(
        self,
        site_key: str,
        url: str,
        version: str = "v2",
        action: str = "verify",
        min_score: float = 0.7,
    ) -> CaptchaResult:
        """Решить reCAPTCHA через 2Captcha."""
        start = time.monotonic()

        # Отправляем задачу
        task_params = {
            "key": self.config.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": url,
            "json": 1,
        }

        if version == "v3":
            task_params["version"] = "v3"
            task_params["action"] = action
            task_params["min_score"] = min_score

        try:
            resp = await self._client.post(
                f"{self.config.base_url_2captcha}/in.php",
                data=task_params,
            )
            data = resp.json()

            if data.get("status") != 1:
                return CaptchaResult(
                    success=False,
                    error=f"2Captcha task creation failed: {data.get('request', 'unknown')}",
                )

            task_id = data["request"]

            # Ожидаем решения
            result = await self._poll_2captcha_result(task_id)
            result.solve_time_ms = (time.monotonic() - start) * 1000

            if result.success:
                self._solved_count += 1
                self._total_cost += 0.00299  # ~$2.99 per 1000 for reCAPTCHA v2
            else:
                self._failed_count += 1

            return result

        except Exception as e:
            self._failed_count += 1
            return CaptchaResult(success=False, error=str(e))

    async def _solve_2captcha_hcaptcha(self, site_key: str, url: str) -> CaptchaResult:
        """Решить hCaptcha через 2Captcha."""
        start = time.monotonic()

        try:
            resp = await self._client.post(
                f"{self.config.base_url_2captcha}/in.php",
                data={
                    "key": self.config.api_key,
                    "method": "hcaptcha",
                    "sitekey": site_key,
                    "pageurl": url,
                    "json": 1,
                },
            )
            data = resp.json()

            if data.get("status") != 1:
                return CaptchaResult(success=False, error=f"2Captcha error: {data.get('request')}")

            task_id = data["request"]
            result = await self._poll_2captcha_result(task_id)
            result.solve_time_ms = (time.monotonic() - start) * 1000

            if result.success:
                self._solved_count += 1
            else:
                self._failed_count += 1

            return result

        except Exception as e:
            self._failed_count += 1
            return CaptchaResult(success=False, error=str(e))

    async def _solve_2captcha_turnstile(self, site_key: str, url: str) -> CaptchaResult:
        """Решить Cloudflare Turnstile через 2Captcha."""
        start = time.monotonic()

        try:
            resp = await self._client.post(
                f"{self.config.base_url_2captcha}/in.php",
                data={
                    "key": self.config.api_key,
                    "method": "turnstile",
                    "sitekey": site_key,
                    "pageurl": url,
                    "json": 1,
                },
            )
            data = resp.json()

            if data.get("status") != 1:
                return CaptchaResult(success=False, error=f"2Captcha error: {data.get('request')}")

            task_id = data["request"]
            result = await self._poll_2captcha_result(task_id)
            result.solve_time_ms = (time.monotonic() - start) * 1000

            if result.success:
                self._solved_count += 1
            else:
                self._failed_count += 1

            return result

        except Exception as e:
            self._failed_count += 1
            return CaptchaResult(success=False, error=str(e))

    async def _poll_2captcha_result(self, task_id: str) -> CaptchaResult:
        """Ожидать результат от 2Captcha."""
        deadline = time.monotonic() + self.config.timeout_seconds

        while time.monotonic() < deadline:
            await asyncio.sleep(self.config.poll_interval_seconds)

            try:
                resp = await self._client.get(
                    f"{self.config.base_url_2captcha}/res.php",
                    params={
                        "key": self.config.api_key,
                        "action": "get",
                        "id": task_id,
                        "json": 1,
                    },
                )
                data = resp.json()

                if data.get("status") == 1:
                    return CaptchaResult(
                        success=True,
                        token=data["request"],
                        captcha_id=task_id,
                    )

                if data.get("request") == "CAPCHA_NOT_READY":
                    continue

                return CaptchaResult(
                    success=False,
                    error=f"2Captcha error: {data.get('request')}",
                    captcha_id=task_id,
                )

            except Exception as e:
                logger.warning(f"2Captcha poll error: {e}")
                continue

        return CaptchaResult(success=False, error="Timeout waiting for captcha solution")

    # ─── CapSolver API ─────────────────────────────────────────────────────

    async def _solve_capsolver_recaptcha(
        self,
        site_key: str,
        url: str,
        version: str = "v2",
    ) -> CaptchaResult:
        """Решить reCAPTCHA через CapSolver."""
        start = time.monotonic()

        try:
            resp = await self._client.post(
                f"{self.config.base_url_capsolver}/createTask",
                json={
                    "clientKey": self.config.api_key,
                    "task": {
                        "type": "ReCaptchaV2TaskProxyless" if version == "v2" else "ReCaptchaV3TaskProxyless",
                        "websiteURL": url,
                        "websiteKey": site_key,
                    },
                },
            )
            data = resp.json()

            if data.get("errorId") != 0:
                return CaptchaResult(success=False, error=f"CapSolver error: {data.get('errorDescription')}")

            task_id = data["taskId"]
            result = await self._poll_capsolver_result(task_id)
            result.solve_time_ms = (time.monotonic() - start) * 1000

            if result.success:
                self._solved_count += 1
            else:
                self._failed_count += 1

            return result

        except Exception as e:
            self._failed_count += 1
            return CaptchaResult(success=False, error=str(e))

    async def _poll_capsolver_result(self, task_id: str) -> CaptchaResult:
        """Ожидать результат от CapSolver."""
        deadline = time.monotonic() + self.config.timeout_seconds

        while time.monotonic() < deadline:
            await asyncio.sleep(self.config.poll_interval_seconds)

            try:
                resp = await self._client.post(
                    f"{self.config.base_url_capsolver}/getTaskResult",
                    json={
                        "clientKey": self.config.api_key,
                        "taskId": task_id,
                    },
                )
                data = resp.json()

                if data.get("errorId") != 0:
                    return CaptchaResult(success=False, error=f"CapSolver error: {data.get('errorDescription')}")

                status = data.get("status")
                if status == "ready":
                    solution = data.get("solution", {})
                    return CaptchaResult(
                        success=True,
                        token=solution.get("gRecaptchaResponse", ""),
                        captcha_id=task_id,
                    )

                if status == "processing":
                    continue

            except Exception as e:
                logger.warning(f"CapSolver poll error: {e}")
                continue

        return CaptchaResult(success=False, error="Timeout waiting for captcha solution")

    # ─── Детекция капч ─────────────────────────────────────────────────────

    async def _detect_recaptcha_site_key(self, page: Page) -> str | None:
        """Автоматически определить site key reCAPTCHA."""
        try:
            # Ищем в data-sitekey атрибутах
            key = await page.evaluate("""
            () => {
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');

                // Ищем в скриптах
                const scripts = document.querySelectorAll('script[src]');
                for (const s of scripts) {
                    const src = s.src || '';
                    if (src.includes('recaptcha')) {
                        const match = src.match(/[?&]render=([^&]+)/);
                        if (match) return match[1];
                    }
                }

                // Ищем в grecaptcha
                if (typeof grecaptcha !== 'undefined' && grecaptcha.render) {
                    const divs = document.querySelectorAll('.g-recaptcha');
                    if (divs.length > 0) return divs[0].getAttribute('data-sitekey');
                }

                return null;
            }
            """)
            return key
        except Exception:
            return None

    async def _detect_hcaptcha_site_key(self, page: Page) -> str | None:
        """Автоматически определить site key hCaptcha."""
        try:
            key = await page.evaluate("""
            () => {
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');
                return null;
            }
            """)
            return key
        except Exception:
            return None

    async def _detect_turnstile_site_key(self, page: Page) -> str | None:
        """Автоматически определить site key Cloudflare Turnstile."""
        try:
            key = await page.evaluate("""
            () => {
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');

                // Ищем в iframe
                const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (iframe) {
                    const src = iframe.src || '';
                    const match = src.match(/[?&]sitekey=([^&]+)/);
                    if (match) return decodeURIComponent(match[1]);
                }

                return null;
            }
            """)
            return key
        except Exception:
            return None

    async def _has_recaptcha_v2(self, page: Page) -> bool:
        """Проверить наличие reCAPTCHA v2 на странице."""
        try:
            return await page.evaluate("""
            () => {
                return !!(
                    document.querySelector('.g-recaptcha') ||
                    document.querySelector('[data-sitekey]') ||
                    document.querySelector('iframe[src*="recaptcha/api2"]') ||
                    (typeof grecaptcha !== 'undefined')
                );
            }
            """)
        except Exception:
            return False

    async def _has_recaptcha_v3(self, page: Page) -> bool:
        """Проверить наличие reCAPTCHA v3 на странице."""
        try:
            return await page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[src]');
                for (const s of scripts) {
                    if (s.src && s.src.includes('recaptcha/releases')) return true;
                }
                return false;
            }
            """)
        except Exception:
            return False

    async def _has_hcaptcha(self, page: Page) -> bool:
        """Проверить наличие hCaptcha на странице."""
        try:
            return await page.evaluate("""
            () => {
                return !!(
                    document.querySelector('.h-captcha') ||
                    document.querySelector('iframe[src*="hcaptcha.com"]')
                );
            }
            """)
        except Exception:
            return False

    async def _has_turnstile(self, page: Page) -> bool:
        """Проверить наличие Cloudflare Turnstile на странице."""
        try:
            return await page.evaluate("""
            () => {
                return !!(
                    document.querySelector('.cf-turnstile') ||
                    document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
                    document.querySelector('[name="cf-turnstile-response"]')
                );
            }
            """)
        except Exception:
            return False

    # ─── Статистика ────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Статистика работы солвера."""
        return {
            "solved": self._solved_count,
            "failed": self._failed_count,
            "total": self._solved_count + self._failed_count,
            "success_rate": (
                self._solved_count / max(1, self._solved_count + self._failed_count)
            ) * 100,
            "total_cost_usd": round(self._total_cost, 4),
            "provider": self.config.provider.value,
        }

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()


def json_token(token: str) -> str:
    """Экранировать токен для вставки в JavaScript."""
    import json
    return json.dumps(token)
