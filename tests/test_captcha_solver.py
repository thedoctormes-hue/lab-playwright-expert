"""
Тесты для CaptchaSolver, CaptchaResult, CaptchaType, SolverProvider, SolverConfig.

Покрывает:
  - CaptchaResult: создание, поля, статусы
  - CaptchaType / SolverProvider: enum значения
  - SolverConfig: конфигурация
  - CaptchaSolver: создание, конфигурация, stats, валидация
"""
import pytest

from lab_playwright_kit.captcha_solver import (
    CaptchaType,
    CaptchaResult,
    CaptchaSolver,
    SolverConfig,
    SolverProvider,
    json_token,
)


# ─── CaptchaType ─────────────────────────────────────────────────────────────

class TestCaptchaType:
    """Тесты enum CaptchaType."""

    def test_all_types_exist(self):
        """Все типы капч определены."""
        expected = {
            "recaptcha_v2", "recaptcha_v3", "hcaptcha",
            "yandex", "cloudflare_turnstile", "funcaptcha",
        }
        actual = {t.value for t in CaptchaType}
        assert actual == expected

    def test_type_values(self):
        """Значения enum."""
        assert CaptchaType.RECAPTCHA_V2 == "recaptcha_v2"
        assert CaptchaType.RECAPTCHA_V3 == "recaptcha_v3"
        assert CaptchaType.HCAPTCHA == "hcaptcha"
        assert CaptchaType.YANDEX == "yandex"
        assert CaptchaType.CLOUDFLARE_TURNSTILE == "cloudflare_turnstile"
        assert CaptchaType.FUNCAPTCHA == "funcaptcha"


# ─── SolverProvider ──────────────────────────────────────────────────────────

class TestSolverProvider:
    """Тесты enum SolverProvider."""

    def test_all_providers_exist(self):
        """Все провайдеры определены."""
        expected = {"2captcha", "capsolver", "anticaptcha"}
        actual = {p.value for p in SolverProvider}
        assert actual == expected

    def test_provider_values(self):
        """Значения провайдеров."""
        assert SolverProvider.TWOCAPTCHA == "2captcha"
        assert SolverProvider.CAPSOLVER == "capsolver"
        assert SolverProvider.ANTICAPTCHA == "anticaptcha"


# ─── CaptchaResult ───────────────────────────────────────────────────────────

class TestCaptchaResult:
    """Тесты dataclass CaptchaResult."""

    def test_default_creation(self):
        """Создание с дефолтными значениями."""
        r = CaptchaResult(success=True)
        assert r.success is True
        assert r.token == ""
        assert r.error == ""
        assert r.solve_time_ms == 0.0
        assert r.cost == 0.0
        assert r.captcha_id == ""

    def test_success_result(self):
        """Успешный результат."""
        r = CaptchaResult(
            success=True,
            token="03AGdBq24PBx...",
            solve_time_ms=15000.0,
            cost=0.00299,
            captcha_id="task_12345",
        )
        assert r.success is True
        assert r.token == "03AGdBq24PBx..."
        assert r.error == ""

    def test_failed_result(self):
        """Неуспешный результат."""
        r = CaptchaResult(success=False, error="Timeout waiting for captcha solution")
        assert r.success is False
        assert r.token == ""
        assert r.error == "Timeout waiting for captcha solution"

    def test_cost_precision(self):
        """Стоимость хранится с точностью float."""
        r = CaptchaResult(success=True, cost=0.00299)
        assert abs(r.cost - 0.00299) < 1e-9


# ─── SolverConfig ────────────────────────────────────────────────────────────

class TestSolverConfig:
    """Тесты dataclass SolverConfig."""

    def test_default_creation(self):
        """Дефолтная конфигурация."""
        c = SolverConfig()
        assert c.provider == SolverProvider.TWOCAPTCHA
        assert c.api_key == ""
        assert c.timeout_seconds == 120
        assert c.poll_interval_seconds == 5.0
        assert c.max_retries == 3

    def test_base_urls(self):
        """Базовые URL провайдеров."""
        c = SolverConfig()
        assert c.base_url_2captcha == "https://2captcha.com"
        assert c.base_url_capsolver == "https://api.capsolver.com"
        assert c.base_url_anticaptcha == "https://api.anti-captcha.com"

    def test_custom_config(self):
        """Кастомная конфигурация."""
        c = SolverConfig(
            provider=SolverProvider.CAPSOLVER,
            api_key="test_key_123",
            timeout_seconds=60,
            poll_interval_seconds=3.0,
            max_retries=5,
        )
        assert c.provider == SolverProvider.CAPSOLVER
        assert c.api_key == "test_key_123"
        assert c.timeout_seconds == 60
        assert c.poll_interval_seconds == 3.0
        assert c.max_retries == 5


# ─── CaptchaSolver ───────────────────────────────────────────────────────────

class TestCaptchaSolver:
    """Тесты CaptchaSolver — создание, конфигурация, stats."""

    def test_default_creation(self):
        """Создание с дефолтными параметрами."""
        solver = CaptchaSolver()
        assert solver.config.provider == SolverProvider.TWOCAPTCHA
        assert solver.config.api_key == ""
        assert solver.config.timeout_seconds == 120

    def test_custom_creation(self):
        """Создание с кастомными параметрами."""
        solver = CaptchaSolver(
            api_key="my_key",
            provider="capsolver",
            timeout=60,
        )
        assert solver.config.api_key == "my_key"
        assert solver.config.provider == SolverProvider.CAPSOLVER
        assert solver.config.timeout_seconds == 60

    def test_2captcha_provider(self):
        """Провайдер 2captcha."""
        solver = CaptchaSolver(provider="2captcha")
        assert solver.config.provider == SolverProvider.TWOCAPTCHA

    def test_capsolver_provider(self):
        """Провайдер capsolver."""
        solver = CaptchaSolver(provider="capsolver")
        assert solver.config.provider == SolverProvider.CAPSOLVER

    def test_anticaptcha_provider(self):
        """Провайдер anticaptcha."""
        solver = CaptchaSolver(provider="anticaptcha")
        assert solver.config.provider == SolverProvider.ANTICAPTCHA

    def test_stats_initial(self):
        """Начальная статистика — всё нули."""
        solver = CaptchaSolver()
        stats = solver.stats
        assert stats["solved"] == 0
        assert stats["failed"] == 0
        assert stats["total"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_cost_usd"] == 0.0
        assert stats["provider"] == "2captcha"

    def test_stats_after_solved(self):
        """Статистика после успешного решения."""
        solver = CaptchaSolver()
        solver._solved_count = 5
        solver._failed_count = 1
        solver._total_cost = 0.01495
        stats = solver.stats
        assert stats["solved"] == 5
        assert stats["failed"] == 1
        assert stats["total"] == 6
        assert abs(stats["success_rate"] - (5 / 6 * 100)) < 0.01

    def test_stats_success_rate_100(self):
        """Success rate 100% при только успехах."""
        solver = CaptchaSolver()
        solver._solved_count = 10
        stats = solver.stats
        assert stats["success_rate"] == 100.0

    def test_stats_success_rate_0(self):
        """Success rate 0% при только провалах."""
        solver = CaptchaSolver()
        solver._failed_count = 5
        stats = solver.stats
        assert stats["success_rate"] == 0.0

    def test_stats_cost_rounding(self):
        """Стоимость округляется до 4 знаков."""
        solver = CaptchaSolver()
        solver._total_cost = 0.12345678
        stats = solver.stats
        assert stats["total_cost_usd"] == 0.1235

    def test_initial_counters_zero(self):
        """Счётчики инициализируются нулями."""
        solver = CaptchaSolver()
        assert solver._solved_count == 0
        assert solver._failed_count == 0
        assert solver._total_cost == 0.0

    def test_config_accessible(self):
        """Конфигурация доступна через solver.config."""
        solver = CaptchaSolver(api_key="test")
        assert solver.config.api_key == "test"
        assert isinstance(solver.config, SolverConfig)


# ─── json_token ──────────────────────────────────────────────────────────────

class TestJsonToken:
    """Тесты функции json_token."""

    def test_simple_token(self):
        """Простой токен."""
        result = json_token("abc123")
        assert result == '"abc123"'

    def test_token_with_special_chars(self):
        """Токен со спецсимволами."""
        result = json_token('a"b\\c')
        assert "a" in result
        assert "\\" in result

    def test_empty_token(self):
        """Пустой токен."""
        result = json_token("")
        assert result == '""'

    def test_token_is_valid_json(self):
        """Результат — валидная JSON строка."""
        import json
        token = "03AGdBq24PBx..."
        result = json_token(token)
        parsed = json.loads(result)
        assert parsed == token

    def test_token_with_newlines(self):
        """Токен с переносами строк."""
        result = json_token("line1\nline2")
        import json
        parsed = json.loads(result)
        assert parsed == "line1\nline2"
