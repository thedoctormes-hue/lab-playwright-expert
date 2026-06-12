"""
BrowserAuthManager — единый фасад для браузерной авторизации на платформах.

Объединяет:
- AccountManager — хранение аккаунтов и кредов
- SessionManager — сохранение/загрузка cookies, localStorage
- AuthTask — выполнение авторизации через браузер
- HumanBehavior — реалистичное поведение при логине
- VPNProxyManager — ротация прокси для обхода блокировок

Поддерживаемые платформы:
- Habr (habr.com) — email + пароль
- VC.ru (vc.ru) — email + пароль
- Telegram (t.me) — через Web версию
- Twitter/X (twitter.com, x.com) — email + пароль
- Любая кастомная платформа через декларативный пресет

Жизненный цикл:
1. Создание аккаунта → AccountManager.create_account()
2. Авторизация → BrowserAuthManager.login(platform, username, password)
3. Сохранение сессии → SessionManager.save_session()
4. Проверка → BrowserAuthManager.check_auth(platform)
5. Использование → BrowserAuthManager.get_authenticated_page(platform)
6. Обновление → BrowserAuthManager.refresh_session(platform)

Использование:
    >>> auth_mgr = BrowserAuthManager(
    ...     browser_manager=bm,
    ...     db_path="/tmp/accounts.db",
    ...     session_dir="/tmp/sessions",
    ... )
    >>> # Авторизация на Хабре
    >>> result = await auth_mgr.login("habr", "user@example.com", "password123")
    >>> if result.success:
    ...     page = await auth_mgr.get_authenticated_page("habr")
    ...     await page.goto("https://habr.com/ru/articles/")
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import BrowserContext, Page

from .account_manager import AccountManager, AccountStatus, Platform
from .session_manager import SessionManager, SessionData
from .task_template import AuthTask, TaskStatus
from .human_behavior import HumanBehaviorEngine


# ─── Auth Result ─────────────────────────────────────────────────────────────

class AuthResultStatus(str, Enum):
    """Статус результата авторизации."""
    SUCCESS = "success"
    FAILED = "failed"
    ALREADY_AUTH = "already_authenticated"
    CAPTCHA = "captcha_required"
    TWO_FA = "2fa_required"
    BLOCKED = "blocked"
    SESSION_EXPIRED = "session_expired"
    NO_CREDENTIALS = "no_credentials"


@dataclass
class AuthResult:
    """Результат операции авторизации.

    Attributes:
        status: Статус результата
        platform: Платформа
        username: Имя пользователя
        message: Человекочитаемое сообщение
        session_name: Имя сохранённой сессии
        cookies_count: Количество сохранённых cookies
        elapsed_seconds: Время выполнения
        error: Текст ошибки (если есть)
        metadata: Дополнительные данные
    """
    status: AuthResultStatus = AuthResultStatus.FAILED
    platform: str = ""
    username: str = ""
    message: str = ""
    session_name: str = ""
    cookies_count: int = 0
    elapsed_seconds: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Авторизация успешна."""
        return self.status in (AuthResultStatus.SUCCESS, AuthResultStatus.ALREADY_AUTH)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "platform": self.platform,
            "username": self.username,
            "message": self.message,
            "session_name": self.session_name,
            "cookies_count": self.cookies_count,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }


# ─── Platform Auth Presets ──────────────────────────────────────────────────

@dataclass
class AuthPreset:
    """Пресет авторизации для платформы.

    Attributes:
        platform: Имя платформы
        login_url: URL страницы логина
        auth_check_url: URL для проверки авторизации
        auth_selectors: Селекторы указывающие на авторизованного пользователя
        username_selector: Селектор поля ввода логина/email
        password_selector: Селектор поля ввода пароля
        submit_selector: Селектор кнопки отправки формы
        success_indicator: Селектор появляющийся после успешного логина
        captcha_selector: Селектор капчи (если есть)
        two_fa_selector: Селектор поля 2FA
        pre_login_actions: Действия перед заполнением формы (клики, ожидания)
        post_login_wait: Дополнительное ожидание после логина (сек)
        use_human_behavior: Использовать имитацию человеческого поведения
        notes: Заметки по авторизации
    """
    platform: str = ""
    login_url: str = ""
    auth_check_url: str = ""
    auth_selectors: list[str] = field(default_factory=list)
    username_selector: str = "input[name='email'], input[type='email']"
    password_selector: str = "input[name='password'], input[type='password']"
    submit_selector: str = "button[type='submit']"
    success_indicator: str = ""
    captcha_selector: str = ""
    two_fa_selector: str = ""
    pre_login_actions: list[dict[str, Any]] = field(default_factory=list)
    post_login_wait: float = 3.0
    use_human_behavior: bool = True
    notes: str = ""


# Пресеты для поддерживаемых платформ
HABR_AUTH_PRESET = AuthPreset(
    platform="habr",
    login_url="https://habr.com/kek/v1/auth/habrahabr/?back=/ru/feed/&hl=ru",
    auth_check_url="https://habr.com/ru/articles/",
    auth_selectors=[
        "a[href*='editor']",
        ".user-panel",
        ".avatar",
        ".user-login",
        "[data-test-id='user-menu']",
        ".btn.btn_blue.btn_habr",
    ],
    username_selector="input[name='email'], input[type='email'], #email, input[placeholder*='mail']",
    password_selector="input[name='password'], input[type='password'], #password, input[placeholder*='пароль']",
    submit_selector="button[type='submit'], .auth-form__button, .m-button, .btn.btn_blue.btn_habr, button:has-text('Войти')",
    success_indicator=".user-panel, .avatar, a[href*='editor']",
    captcha_selector=".captcha, .g-recaptcha, iframe[src*='recaptcha'], iframe[src*='hcaptcha'], :text('Необходимо пройти капчу')",
    two_fa_selector="input[name='code'], input[name='otp'], .two-factor",
    pre_login_actions=[
        {"action": "wait", "timeout": 5000},
    ],
    post_login_wait=5.0,
    use_human_behavior=True,
    notes=(
        "Habr: email + пароль. "
        "Авторизация через account.habr.com (редирект с /kek/v1/auth/habrahabr/). "
        "Может потребовать капчу при входе с незнакомого IP. "
        "Рекомендуется использовать engine='cloakbrowser' + persistent profile."
    ),
)

VCRU_AUTH_PRESET = AuthPreset(
    platform="vcru",
    login_url="https://vc.ru/?modal=auth",
    auth_check_url="https://vc.ru/write",
    auth_selectors=[
        ".user-menu",
        ".avatar",
        "a[href*='write']",
        ".user_login",
        ".b-user-menu",
        "a[href*='editor']",
    ],
    username_selector="input[name='email'], input[name='login'], input[type='email'], input[placeholder*='mail']",
    password_selector="input[name='password'], input[type='password'], input[placeholder*='пароль']",
    submit_selector="button[type='submit'], .button, input[type='submit'], button:has-text('Войти'), .button--type-primary",
    success_indicator=".user-menu, .avatar, a[href*='write']",
    captcha_selector=".captcha, .g-recaptcha",
    two_fa_selector="input[name='code'], input[name='otp']",
    pre_login_actions=[
        {"action": "wait", "timeout": 3000},
    ],
    post_login_wait=4.0,
    use_human_behavior=True,
    notes="VC.ru: модальное окно авторизации. Найден индикатор a[href*='editor'] на неавторизованной странице — использовать для проверки.",
)

TWITTER_AUTH_PRESET = AuthPreset(
    platform="twitter",
    login_url="https://x.com/i/flow/login",
    auth_check_url="https://x.com/home",
    auth_selectors=[
        "[data-testid='SideNav_AccountSwitcher_Button']",
        "[data-testid='AppTabBar_Home_Link']",
        "a[href='/compose/tweet']",
        "[data-testid='primaryColumn']",
    ],
    username_selector="input[autocomplete='username'], input[name='text']",
    password_selector="input[name='password'], input[type='password']",
    submit_selector="button[data-testid='LoginForm_Login_Button'], button:has-text('Next'), button:has-text('Log in')",
    success_indicator="[data-testid='SideNav_AccountSwitcher_Button'], [data-testid='AppTabBar_Home_Link']",
    captcha_selector="iframe[title*='recaptcha'], .captcha",
    two_fa_selector="input[name='challenge_response'], input[autocomplete='one-time-code']",
    pre_login_actions=[
        {"action": "wait", "selector": "input[autocomplete='username']", "timeout": 15000},
    ],
    post_login_wait=6.0,
    use_human_behavior=True,
    notes="Twitter/X: многоступенчатый логин. Сначала username (input[name='text']), потом password. Кнопка 'Next' → 'Log in'. Может потребовать 2FA. Cookie banner нужно закрыть.",
)

TELEGRAM_AUTH_PRESET = AuthPreset(
    platform="telegram",
    login_url="https://web.telegram.org/",
    auth_check_url="https://web.telegram.org/",
    auth_selectors=[
        ".chat-list",
        ".sidebar-header",
        "[class*='chatlist']",
        ".im_dialogs_wrap",
        ".ChatFolders",
        ".LeftColumn",
    ],
    username_selector="input[name='phone_number'], input[type='tel'], input[placeholder*='phone']",
    password_selector="input[name='password'], input[type='password']",
    submit_selector="button[type='submit'], .btn-primary, .btn-primary-transparent, button:has-text('Log in')",
    success_indicator=".chat-list, .sidebar-header, .ChatFolders",
    captcha_selector=".captcha, iframe[title*='captcha']",
    two_fa_selector="input[name='code'], input[type='tel']",
    pre_login_actions=[
        {"action": "click", "selector": "button:has-text('LOG IN BY PHONE NUMBER')"},
        {"action": "wait", "selector": "input[type='tel']", "timeout": 10000},
    ],
    post_login_wait=8.0,
    use_human_behavior=True,
    notes="Telegram Web: сначала клик 'LOG IN BY PHONE NUMBER', потом ввод телефона. Код приходит в приложение. Сессия хранится долго. Индикаторы: .sidebar-header, .ChatFolders.",
)


# Регистр пресетов
AUTH_PRESETS: dict[str, AuthPreset] = {
    "habr": HABR_AUTH_PRESET,
    "vcru": VCRU_AUTH_PRESET,
    "twitter": TWITTER_AUTH_PRESET,
    "x": TWITTER_AUTH_PRESET,
    "telegram": TELEGRAM_AUTH_PRESET,
}


# ─── BrowserAuthManager ─────────────────────────────────────────────────────

class BrowserAuthManager:
    """Единый фасад для браузерной авторизации на платформах.

    Управляет полным жизненным циклом:
    - Создание и хранение аккаунтов
    - Авторизация через браузер с имитацией человеческого поведения
    - Сохранение и восстановление сессий (cookies, localStorage)
    - Проверка валидности сессий
    - Ротация аккаунтов и прокси

    Использование:
        >>> auth_mgr = BrowserAuthManager(browser_manager)
        >>> # Быстрая авторизация
        >>> result = await auth_mgr.login("habr", "user@mail.ru", "pass")
        >>> if result.success:
        ...     page = await auth_mgr.get_authenticated_page("habr")
        >>> # Проверка существующей сессии
        >>> if await auth_mgr.check_auth("habr", "user@mail.ru"):
        ...     print("Уже авторизован!")
    """

    def __init__(
        self,
        browser_manager: Any,
        db_path: str = "accounts.db",
        session_dir: str = ".sessions",
        proxy_manager: Any | None = None,
        default_ttl: int = 86400 * 7,  # 7 дней
    ):
        """
        Args:
            browser_manager: Экземпляр BrowserManager
            db_path: Путь к БД аккаунтов (SQLite)
            session_dir: Директория для хранения сессий
            proxy_manager: VPNProxyManager для ротации прокси
            default_ttl: TTL сессии по умолчанию (сек)
        """
        from .browser import BrowserManager
        self._browser_mgr: BrowserManager = browser_manager
        self._account_mgr = AccountManager(db_path=db_path)
        self._session_mgr = SessionManager(storage_dir=session_dir)
        self._proxy_manager = proxy_manager
        self._default_ttl = default_ttl
        self._active_sessions: dict[str, SessionData] = {}

    @property
    def accounts(self) -> AccountManager:
        """Менеджер аккаунтов."""
        return self._account_mgr

    @property
    def sessions(self) -> SessionManager:
        """Менеджер сессий."""
        return self._session_mgr

    # ─── Account CRUD ────────────────────────────────────────────────────

    def create_account(
        self,
        platform: str,
        username: str,
        password: str = "",
        email: str = "",
        phone: str = "",
        proxy_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Создать аккаунт в БД.

        Args:
            platform: Платформа (habr, vcru, twitter, telegram, ...)
            username: Имя пользователя / логин
            password: пароль (будет зашифрован)
            email: email (опционально)
            phone: телефон (опционально)
            proxy_url: прокси для аккаунта
            metadata: дополнительные данные

        Returns:
            ID созданного аккаунта
        """
        account_id = self._account_mgr.create_account(
            platform=platform,
            username=username,
            password=password,
            email=email or username,
            phone=phone,
            proxy_url=proxy_url,
        )

        if metadata:
            self._account_mgr.update_metadata(account_id, metadata)

        logger.info(f"Account created: {platform}/{username} (id={account_id})")
        return account_id

    def get_account(self, platform: str, username: str) -> Any | None:
        """Получить аккаунт по платформе и имени."""
        return self._account_mgr.get_account(platform, username)

    def list_accounts(self, platform: str = "", status: str = "") -> list[Any]:
        """Список аккаунтов с фильтрацией."""
        return self._account_mgr.list_accounts(platform=platform, status=status)

    # ─── Login ───────────────────────────────────────────────────────────

    async def login(
        self,
        platform: str,
        username: str,
        password: str,
        *,
        preset: AuthPreset | None = None,
        use_human_behavior: bool = True,
        force: bool = False,
        proxy_url: str = "",
    ) -> AuthResult:
        """Выполнить авторизацию на платформе.

        Полный цикл:
        1. Проверить существующую сессию (если не force)
        2. Загрузить пресет платформы
        3. Перейти на страницу логина
        4. Заполнить форму (с human behavior)
        5. Обработать капчу/2FA если нужно
        6. Проверить успешность
        7. Сохранить сессию

        Args:
            platform: Платформа (habr, vcru, twitter, telegram)
            username: Логин / email
            password: Пароль
            preset: Кастомный пресет (если не из стандартных)
            use_human_behavior: Использовать имитацию человека
            force: Принудительная переавторизация
            proxy_url: Прокси для этой сессии

        Returns:
            AuthResult с результатом
        """
        start_time = time.time()
        platform_lower = platform.lower()

        # 1. Проверить существующую сессию
        if not force:
            session_name = f"{platform_lower}_{username}"
            if await self._try_load_session(session_name):
                logger.info(f"Session restored: {session_name}")
                return AuthResult(
                    status=AuthResultStatus.ALREADY_AUTH,
                    platform=platform_lower,
                    username=username,
                    message="Session restored from cache",
                    session_name=session_name,
                    elapsed_seconds=time.time() - start_time,
                )

        # 2. Загрузить пресет
        auth_preset = preset or AUTH_PRESETS.get(platform_lower)
        if not auth_preset:
            return AuthResult(
                status=AuthResultStatus.FAILED,
                platform=platform_lower,
                username=username,
                error=f"No auth preset for platform: {platform_lower}",
                elapsed_seconds=time.time() - start_time,
            )

        # 3. Выполнить логин
        try:
            page = await self._browser_mgr.new_page()

            # Human behavior
            behavior = HumanBehaviorEngine(page) if use_human_behavior else None

            # Перейти на страницу логина
            logger.info(f"Navigating to {auth_preset.login_url}")
            await page.goto(auth_preset.login_url, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

            # Pre-login actions
            for action in auth_preset.pre_login_actions:
                await self._execute_pre_action(page, action)

            # Заполнить логин
            if behavior:
                await behavior.move_mouse_to_element(auth_preset.username_selector)
                await behavior.type_text(username, selector=auth_preset.username_selector)
            else:
                await page.fill(auth_preset.username_selector, username)

            await asyncio.sleep(0.5)

            # Twitter: многоступенчатый логин — сначала username, потом Next
            if platform_lower in ("twitter", "x"):
                try:
                    next_btn = page.locator(
                        "[data-testid='ocfEnterTextNextButton'], "
                        "button:has-text('Next'), "
                        "button:has-text('Далее')"
                    ).first
                    if await next_btn.is_visible(timeout=3000):
                        if behavior:
                            await behavior.click_element(next_btn)
                        else:
                            await next_btn.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass

            # Заполнить пароль
            if behavior:
                await behavior.move_mouse_to_element(auth_preset.password_selector)
                await behavior.type_text(password, selector=auth_preset.password_selector)
            else:
                await page.fill(auth_preset.password_selector, password)

            await asyncio.sleep(0.5)

            # Нажать submit
            if behavior:
                await behavior.click_element(auth_preset.submit_selector)
            else:
                await page.click(auth_preset.submit_selector)

            # Ждём результата
            await asyncio.sleep(auth_preset.post_login_wait)

            # 4. Проверить капчу
            if auth_preset.captcha_selector:
                try:
                    captcha_el = page.locator(auth_preset.captcha_selector).first
                    if await captcha_el.is_visible(timeout=3000):
                        logger.warning(f"Captcha detected on {platform_lower}")
                        return AuthResult(
                            status=AuthResultStatus.CAPTCHA,
                            platform=platform_lower,
                            username=username,
                            message="Captcha required — solve manually or use captcha_solver",
                            elapsed_seconds=time.time() - start_time,
                        )
                except Exception:
                    pass

            # 5. Проверить 2FA
            if auth_preset.two_fa_selector:
                try:
                    two_fa_el = page.locator(auth_preset.two_fa_selector).first
                    if await two_fa_el.is_visible(timeout=3000):
                        logger.warning(f"2FA required on {platform_lower}")
                        return AuthResult(
                            status=AuthResultStatus.TWO_FA,
                            platform=platform_lower,
                            username=username,
                            message="2FA required — provide code via handle_2fa()",
                            elapsed_seconds=time.time() - start_time,
                        )
                except Exception:
                    pass

            # 6. Проверить успешность
            is_auth = await self._verify_auth(page, auth_preset)

            if not is_auth:
                # Подождём ещё — иногда редирект медленный
                await asyncio.sleep(3)
                is_auth = await self._verify_auth(page, auth_preset)

            if not is_auth:
                return AuthResult(
                    status=AuthResultStatus.FAILED,
                    platform=platform_lower,
                    username=username,
                    message="Auth verification failed — check credentials or selectors",
                    elapsed_seconds=time.time() - start_time,
                )

            # 7. Сохранить сессию
            session_name = f"{platform_lower}_{username}"
            cookies = await page.context.cookies()
            await self._session_mgr.save_session(
                page,
                session_name,
                ttl_seconds=self._default_ttl,
                metadata={
                    "platform": platform_lower,
                    "username": username,
                    "proxy_url": proxy_url,
                },
            )

            # Обновить статус аккаунта
            account = self._account_mgr.get_account(platform_lower, username)
            if account:
                self._account_mgr.update_status(account.id, AccountStatus.ACTIVE)
                self._account_mgr.update_last_used(account.id)

            elapsed = time.time() - start_time
            logger.info(f"Auth success: {platform_lower}/{username} ({elapsed:.1f}s)")

            return AuthResult(
                status=AuthResultStatus.SUCCESS,
                platform=platform_lower,
                username=username,
                message="Authentication successful",
                session_name=session_name,
                cookies_count=len(cookies),
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Auth failed: {platform_lower}/{username}: {e}")
            return AuthResult(
                status=AuthResultStatus.FAILED,
                platform=platform_lower,
                username=username,
                error=str(e),
                elapsed_seconds=elapsed,
            )

    # ─── 2FA Handler ─────────────────────────────────────────────────────

    async def handle_2fa(
        self,
        platform: str,
        username: str,
        code: str,
        two_fa_selector: str = "",
    ) -> AuthResult:
        """Обработать 2FA код после логина.

        Вызывать после login() вернул AuthResultStatus.TWO_FA.

        Args:
            platform: Платформа
            username: Логин
            code: 2FA код
            two_fa_selector: Селектор поля ввода кода

        Returns:
            AuthResult
        """
        start_time = time.time()
        platform_lower = platform.lower()
        preset = AUTH_PRESETS.get(platform_lower)
        selector = two_fa_selector or (preset.two_fa_selector if preset else "")

        if not selector:
            return AuthResult(
                status=AuthResultStatus.FAILED,
                platform=platform_lower,
                username=username,
                error="No 2FA selector configured",
            )

        try:
            page = await self._browser_mgr.current_page()
            if not page:
                return AuthResult(
                    status=AuthResultStatus.FAILED,
                    platform=platform_lower,
                    username=username,
                    error="No active page",
                )

            await page.fill(selector, code)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

            # Проверить успешность
            if preset:
                is_auth = await self._verify_auth(page, preset)
                if is_auth:
                    session_name = f"{platform_lower}_{username}"
                    cookies = await page.context.cookies()
                    await self._session_mgr.save_session(
                        page, session_name,
                        ttl_seconds=self._default_ttl,
                        metadata={"platform": platform_lower, "username": username},
                    )
                    return AuthResult(
                        status=AuthResultStatus.SUCCESS,
                        platform=platform_lower,
                        username=username,
                        message="2FA completed successfully",
                        session_name=session_name,
                        cookies_count=len(cookies),
                        elapsed_seconds=time.time() - start_time,
                    )

            return AuthResult(
                status=AuthResultStatus.FAILED,
                platform=platform_lower,
                username=username,
                message="2FA verification failed",
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            return AuthResult(
                status=AuthResultStatus.FAILED,
                platform=platform_lower,
                username=username,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    # ─── Check Auth ──────────────────────────────────────────────────────

    async def check_auth(
        self,
        platform: str,
        username: str = "",
    ) -> bool:
        """Проверить авторизацию на платформе.

        Сначала проверяет сохранённую сессию, потом — через браузер.

        Args:
            platform: Платформа
            username: Логин (опционально — проверяет любую сессию платформы)

        Returns:
            True если авторизован
        """
        platform_lower = platform.lower()
        preset = AUTH_PRESETS.get(platform_lower)
        if not preset:
            logger.warning(f"No preset for {platform_lower}, cannot check auth")
            return False

        # Проверить сохранённые сессии
        sessions = self._session_mgr.list_sessions()
        for sess_name in sessions:
            if sess_name.startswith(f"{platform_lower}_"):
                if username and not sess_name.endswith(f"_{username}"):
                    continue
                if await self._try_load_session(sess_name):
                    return True

        # Проверить через браузер
        try:
            page = await self._browser_mgr.new_page()
            return await self._verify_auth(page, preset)
        except Exception:
            return False

    # ─── Get Authenticated Page ──────────────────────────────────────────

    async def get_authenticated_page(
        self,
        platform: str,
        username: str,
        target_url: str = "",
    ) -> Page | None:
        """Получить авторизованную страницу для платформы.

        Восстанавливает сессию из кэша или возвращает текущую страницу.

        Args:
            platform: Платформа
            username: Логин
            target_url: URL для перехода после восстановления сессии

        Returns:
            Page или None
        """
        platform_lower = platform.lower()
        session_name = f"{platform_lower}_{username}"

        try:
            page = await self._browser_mgr.new_page()

            # Попытаться загрузить сессию
            loaded = await self._session_mgr.load_session(page, session_name)
            if not loaded:
                logger.warning(f"No saved session: {session_name}")
                return None

            # Перейти на целевую страницу
            if target_url:
                await page.goto(target_url, wait_until="domcontentloaded")
                await asyncio.sleep(1)

            # Верификация
            preset = AUTH_PRESETS.get(platform_lower)
            if preset:
                is_auth = await self._verify_auth(page, preset)
                if not is_auth:
                    logger.warning(f"Session expired: {session_name}")
                    self._session_mgr.delete_session(session_name)
                    return None

            logger.info(f"Authenticated page ready: {session_name}")
            return page

        except Exception as e:
            logger.error(f"Failed to get authenticated page: {e}")
            return None

    # ─── Session Management ──────────────────────────────────────────────

    async def save_session(
        self,
        platform: str,
        username: str,
        page: Page | None = None,
        ttl: int = 0,
    ) -> str:
        """Сохранить текущую сессию.

        Args:
            platform: Платформа
            username: Логин
            page: Страница (None = текущая)
            ttl: TTL в секундах (0 = default)

        Returns:
            Имя сессии
        """
        platform_lower = platform.lower()
        session_name = f"{platform_lower}_{username}"
        ttl = ttl or self._default_ttl

        if not page:
            page = await self._browser_mgr.current_page()
            if not page:
                raise RuntimeError("No active page to save session from")

        await self._session_mgr.save_session(
            page,
            session_name,
            ttl_seconds=ttl,
            metadata={"platform": platform_lower, "username": username},
        )
        return session_name

    async def refresh_session(self, platform: str, username: str, password: str) -> AuthResult:
        """Обновить сессию — удалить старую и выполнить переавторизацию."""
        platform_lower = platform.lower()
        session_name = f"{platform_lower}_{username}"
        self._session_mgr.delete_session(session_name)
        return await self.login(platform_lower, username, password, force=True)

    def delete_session(self, platform: str, username: str) -> None:
        """Удалить сохранённую сессию."""
        session_name = f"{platform}_{username}"
        self._session_mgr.delete_session(session_name)

    def list_sessions(self, platform: str = "") -> list[str]:
        """Список сохранённых сессий."""
        all_sessions = self._session_mgr.list_sessions()
        if platform:
            prefix = f"{platform}_"
            return [s for s in all_sessions if s.startswith(prefix)]
        return all_sessions

    # ─── Preset Management ───────────────────────────────────────────────

    @staticmethod
    def register_preset(name: str, preset: AuthPreset) -> None:
        """Зарегистрировать кастомный пресет авторизации."""
        AUTH_PRESETS[name.lower()] = preset
        logger.info(f"Auth preset registered: {name}")

    @staticmethod
    def get_preset(platform: str) -> AuthPreset | None:
        """Получить пресет по имени платформы."""
        return AUTH_PRESETS.get(platform.lower())

    @staticmethod
    def list_presets() -> list[str]:
        """Список всех зарегистрированных пресетов."""
        return list(AUTH_PRESETS.keys())

    # ─── Internal ────────────────────────────────────────────────────────

    async def _verify_auth(self, page: Page, preset: AuthPreset) -> bool:
        """Проверить авторизацию через селекторы на текущей странице."""
        # Сначала проверить success_indicator
        if preset.success_indicator:
            try:
                el = page.locator(preset.success_indicator).first
                if await el.is_visible(timeout=5000):
                    return True
            except Exception:
                pass

        # Проверить auth_selectors
        for sel in preset.auth_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    return True
            except Exception:
                continue

        return False

    async def _try_load_session(self, session_name: str) -> bool:
        """Попытаться загрузить сессию из кэша."""
        try:
            session_data = self._session_mgr.get_session(session_name)
            if not session_data or session_data.is_expired:
                return False
            self._active_sessions[session_name] = session_data
            return True
        except Exception:
            return False

    async def _execute_pre_action(self, page: Page, action: dict[str, Any]) -> None:
        """Выполнить pre-login действие."""
        action_type = action.get("action", "")
        if action_type == "wait":
            selector = action.get("selector", "")
            timeout = action.get("timeout", 10000)
            if selector:
                await page.wait_for_selector(selector, timeout=timeout)
        elif action_type == "click":
            selector = action.get("selector", "")
            if selector:
                await page.click(selector)
                await asyncio.sleep(0.5)
        elif action_type == "sleep":
            seconds = action.get("seconds", 1)
            await asyncio.sleep(seconds)
