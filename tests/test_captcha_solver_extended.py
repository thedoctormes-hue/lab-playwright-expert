"""
Расширенные тесты для CaptchaSolver.

Покрывает:
  - CaptchaResult dataclass
  - SolverConfig defaults
  - CaptchaSolver.__init__, stats, close
  - CaptchaSolver.inject_*_token (page.evaluate мок)
  - CaptchaSolver.auto_solve (detection + routing)
  - CaptchaSolver._detect_*_site_key
  - CaptchaSolver._has_* detection methods
  - CaptchaSolver._solve_2captcha_* (HTTP мок)
  - CaptchaSolver._poll_2captcha_result
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lab_playwright_kit.captcha_solver import (
    CaptchaResult,
    CaptchaSolver,
    CaptchaType,
    SolverConfig,
    SolverProvider,
    json_token,
)


# ─── CaptchaResult ──────────────────────────────────────────────────────────


class TestCaptchaResult:
    def test_defaults(self):
        r = CaptchaResult(success=True)
        assert r.success is True
        assert r.token == ""
        assert r.error == ""
        assert r.solve_time_ms == 0.0
        assert r.cost == 0.0
        assert r.captcha_id == ""

    def test_all_fields(self):
        r = CaptchaResult(
            success=True,
            token="abc123",
            error="",
            solve_time_ms=5432.1,
            cost=0.003,
            captcha_id="task_42",
        )
        assert r.token == "abc123"
        assert r.solve_time_ms == 5432.1
        assert r.cost == 0.003
        assert r.captcha_id == "task_42"

    def test_failure(self):
        r = CaptchaResult(success=False, error="Timeout")
        assert r.success is False
        assert r.error == "Timeout"
        assert r.token == ""


# ─── SolverConfig ───────────────────────────────────────────────────────────


class TestSolverConfig:
    def test_defaults(self):
        cfg = SolverConfig()
        assert cfg.provider == SolverProvider.TWOCAPTCHA
        assert cfg.api_key == ""
        assert cfg.timeout_seconds == 120
        assert cfg.poll_interval_seconds == 5.0
        assert cfg.max_retries == 3

    def test_custom(self):
        cfg = SolverConfig(
            provider=SolverProvider.CAPSOLVER,
            api_key="key123",
            timeout_seconds=60,
        )
        assert cfg.provider == SolverProvider.CAPSOLVER
        assert cfg.api_key == "key123"
        assert cfg.timeout_seconds == 60

    def test_base_urls(self):
        cfg = SolverConfig()
        assert "2captcha.com" in cfg.base_url_2captcha
        assert "capsolver.com" in cfg.base_url_capsolver
        assert "anti-captcha.com" in cfg.base_url_anticaptcha


# ─── SolverProvider / CaptchaType enums ─────────────────────────────────────


class TestEnums:
    def test_solver_provider_values(self):
        assert SolverProvider.TWOCAPTCHA.value == "2captcha"
        assert SolverProvider.CAPSOLVER.value == "capsolver"
        assert SolverProvider.ANTICAPTCHA.value == "anticaptcha"

    def test_captcha_type_values(self):
        assert CaptchaType.RECAPTCHA_V2.value == "recaptcha_v2"
        assert CaptchaType.RECAPTCHA_V3.value == "recaptcha_v3"
        assert CaptchaType.HCAPTCHA.value == "hcaptcha"
        assert CaptchaType.CLOUDFLARE_TURNSTILE.value == "cloudflare_turnstile"
        assert CaptchaType.YANDEX.value == "yandex"
        assert CaptchaType.FUNCAPTCHA.value == "funcaptcha"


# ─── CaptchaSolver init & stats ────────────────────────────────────────────


class TestCaptchaSolverInit:
    def test_default_init(self):
        solver = CaptchaSolver()
        assert solver.config.provider == SolverProvider.TWOCAPTCHA
        assert solver.config.api_key == ""
        assert solver.config.timeout_seconds == 120

    def test_custom_init(self):
        solver = CaptchaSolver(api_key="test_key", provider="capsolver", timeout=60)
        assert solver.config.api_key == "test_key"
        assert solver.config.provider == SolverProvider.CAPSOLVER
        assert solver.config.timeout_seconds == 60

    def test_stats_initial(self):
        solver = CaptchaSolver()
        stats = solver.stats
        assert stats["solved"] == 0
        assert stats["failed"] == 0
        assert stats["total"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_cost_usd"] == 0.0

    def test_stats_after_solve(self):
        solver = CaptchaSolver()
        solver._solved_count = 5
        solver._failed_count = 2
        solver._total_cost = 0.015
        stats = solver.stats
        assert stats["solved"] == 5
        assert stats["failed"] == 2
        assert stats["total"] == 7
        assert abs(stats["success_rate"] - 71.428) < 0.01

    @pytest.mark.asyncio
    async def test_close(self):
        solver = CaptchaSolver()
        solver._client = AsyncMock()
        solver._client.aclose = AsyncMock()
        await solver.close()
        solver._client.aclose.assert_called_once()


# ─── Inject token methods ──────────────────────────────────────────────────


class TestInjectTokens:
    @pytest.mark.asyncio
    async def test_inject_recaptcha_token(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock()
        await solver.inject_recaptcha_token(page, "test_token_123")
        page.evaluate.assert_called_once()
        call_args = page.evaluate.call_args[0][0]
        assert "test_token_123" in call_args
        assert "g-recaptcha-response" in call_args

    @pytest.mark.asyncio
    async def test_inject_hcaptcha_token(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock()
        await solver.inject_hcaptcha_token(page, "hc_token_456")
        page.evaluate.assert_called_once()
        call_args = page.evaluate.call_args[0][0]
        assert "hc_token_456" in call_args
        assert "h-captcha-response" in call_args

    @pytest.mark.asyncio
    async def test_inject_turnstile_token(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock()
        await solver.inject_turnstile_token(page, "turn_token_789")
        page.evaluate.assert_called_once()
        call_args = page.evaluate.call_args[0][0]
        assert "turn_token_789" in call_args
        assert "cf-turnstile-response" in call_args


# ─── Detection methods ─────────────────────────────────────────────────────


class TestDetection:
    @pytest.mark.asyncio
    async def test_detect_recaptcha_site_key_found(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="6Lc_test_key")
        key = await solver._detect_recaptcha_site_key(page)
        assert key == "6Lc_test_key"

    @pytest.mark.asyncio
    async def test_detect_recaptcha_site_key_not_found(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=None)
        key = await solver._detect_recaptcha_site_key(page)
        assert key is None

    @pytest.mark.asyncio
    async def test_detect_hcaptcha_site_key_found(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="hc_key_123")
        key = await solver._detect_hcaptcha_site_key(page)
        assert key == "hc_key_123"

    @pytest.mark.asyncio
    async def test_detect_turnstile_site_key_found(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="turn_key_456")
        key = await solver._detect_turnstile_site_key(page)
        assert key == "turn_key_456"

    @pytest.mark.asyncio
    async def test_has_recaptcha_v2_true(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=True)
        result = await solver._has_recaptcha_v2(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_recaptcha_v2_false(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=False)
        result = await solver._has_recaptcha_v2(page)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_hcaptcha_true(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=True)
        result = await solver._has_hcaptcha(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_turnstile_true(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=True)
        result = await solver._has_turnstile(page)
        assert result is True


# ─── Auto-solve ────────────────────────────────────────────────────────────


class TestAutoSolve:
    @pytest.mark.asyncio
    async def test_auto_solve_recaptcha_v2(self):
        solver = CaptchaSolver(api_key="test_key")
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(
            side_effect=[
                True,  # _has_recaptcha_v2
            ]
        )
        solver._detect_recaptcha_site_key = AsyncMock(return_value="key123")
        solver._solve_2captcha_recaptcha = AsyncMock(
            return_value=CaptchaResult(success=True, token="tok_123")
        )
        result = await solver.auto_solve(page)
        assert result.success is True
        assert result.token == "tok_123"

    @pytest.mark.asyncio
    async def test_auto_solve_no_captcha(self):
        solver = CaptchaSolver()
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=False)
        result = await solver.auto_solve(page)
        assert result.success is False
        assert "No captcha detected" in result.error

    @pytest.mark.asyncio
    async def test_auto_solve_hcaptcha(self):
        solver = CaptchaSolver(api_key="test_key")
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(
            side_effect=[
                False,  # _has_recaptcha_v2
                False,  # _has_recaptcha_v3
                True,  # _has_hcaptcha
            ]
        )
        solver._detect_hcaptcha_site_key = AsyncMock(return_value="hc_key")
        solver._solve_2captcha_hcaptcha = AsyncMock(
            return_value=CaptchaResult(success=True, token="hc_tok")
        )
        result = await solver.auto_solve(page)
        assert result.success is True
        assert result.token == "hc_tok"


# ─── 2Captcha API (mocked HTTP) ───────────────────────────────────────────


class Test2CaptchaAPI:
    @pytest.mark.asyncio
    async def test_solve_2captcha_recaptcha_success(self):
        solver = CaptchaSolver(api_key="test_key")
        mock_resp_in = MagicMock()
        mock_resp_in.json.return_value = {"status": 1, "request": "task_42"}
        mock_resp_res = MagicMock()
        mock_resp_res.json.return_value = {"status": 1, "request": "token_abc"}

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_resp_in)
        solver._client.get = AsyncMock(return_value=mock_resp_res)

        with patch("lab_playwright_kit.captcha_solver.asyncio.sleep", new_callable=AsyncMock):
            result = await solver._solve_2captcha_recaptcha("site_key", "https://example.com")

        assert result.success is True
        assert result.token == "token_abc"
        assert result.captcha_id == "task_42"
        assert solver._solved_count == 1

    @pytest.mark.asyncio
    async def test_solve_2captcha_recaptcha_task_fail(self):
        solver = CaptchaSolver(api_key="test_key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST"}

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_resp)

        result = await solver._solve_2captcha_recaptcha("bad_key", "https://example.com")
        assert result.success is False
        assert "ERROR_KEY_DOES_NOT_EXIST" in result.error
        # Note: _failed_count is NOT incremented on task creation failure (early return)
        assert solver._failed_count == 0

    @pytest.mark.asyncio
    async def test_poll_2captcha_result_success(self):
        solver = CaptchaSolver(api_key="test_key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": 1, "request": "token_xyz"}

        solver._client = AsyncMock()
        solver._client.get = AsyncMock(return_value=mock_resp)

        result = await solver._poll_2captcha_result("task_99")
        assert result.success is True
        assert result.token == "token_xyz"

    @pytest.mark.asyncio
    async def test_poll_2captcha_result_not_ready_then_ready(self):
        solver = CaptchaSolver(api_key="test_key")
        resp_not_ready = MagicMock()
        resp_not_ready.json.return_value = {"request": "CAPCHA_NOT_READY"}
        resp_ready = MagicMock()
        resp_ready.json.return_value = {"status": 1, "request": "token_ready"}

        solver._client = AsyncMock()
        solver._client.get = AsyncMock(side_effect=[resp_not_ready, resp_ready])

        with patch("lab_playwright_kit.captcha_solver.asyncio.sleep", new_callable=AsyncMock):
            result = await solver._poll_2captcha_result("task_55")

        assert result.success is True
        assert result.token == "token_ready"

    @pytest.mark.asyncio
    async def test_solve_2captcha_hcaptcha_success(self):
        solver = CaptchaSolver(api_key="test_key")
        mock_resp_in = MagicMock()
        mock_resp_in.json.return_value = {"status": 1, "request": "task_hc"}
        mock_resp_res = MagicMock()
        mock_resp_res.json.return_value = {"status": 1, "request": "hc_token"}

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_resp_in)
        solver._client.get = AsyncMock(return_value=mock_resp_res)

        with patch("lab_playwright_kit.captcha_solver.asyncio.sleep", new_callable=AsyncMock):
            result = await solver._solve_2captcha_hcaptcha("hc_site_key", "https://example.com")

        assert result.success is True
        assert solver._solved_count == 1

    @pytest.mark.asyncio
    async def test_solve_2captcha_turnstile_success(self):
        solver = CaptchaSolver(api_key="test_key")
        mock_resp_in = MagicMock()
        mock_resp_in.json.return_value = {"status": 1, "request": "task_turn"}
        mock_resp_res = MagicMock()
        mock_resp_res.json.return_value = {"status": 1, "request": "turn_token"}

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_resp_in)
        solver._client.get = AsyncMock(return_value=mock_resp_res)

        with patch("lab_playwright_kit.captcha_solver.asyncio.sleep", new_callable=AsyncMock):
            result = await solver._solve_2captcha_turnstile("turn_site_key", "https://example.com")

        assert result.success is True
        assert solver._solved_count == 1


# ─── json_token helper ─────────────────────────────────────────────────────


class TestJsonToken:
    def test_simple_token(self):
        result = json_token("abc123")
        assert result == '"abc123"'

    def test_token_with_special_chars(self):
        result = json_token('token"with\\special')
        assert "token" in result  # json.dumps escapes properly

    def test_empty_token(self):
        result = json_token("")
        assert result == '""'
