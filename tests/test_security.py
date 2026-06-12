"""
Тесты безопасности для screenshot_service.
SSRF protection, аутентификация, rate limiting.
"""
import os
import sys

import pytest


# Добавить scripts в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.screenshot_service import URLValidationError, validate_url


# ─── SSRF Protection Tests ───

class TestSSRFProtection:
    """Тесты защиты от SSRF атак."""

    def test_blocks_file_scheme(self):
        """Блокировка file:// протокола."""
        with pytest.raises(URLValidationError, match="не разрешена"):
            validate_url("file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        """Блокировка ftp:// протокола."""
        with pytest.raises(URLValidationError, match="не разрешена"):
            validate_url("ftp://internal.server/file")

    def test_blocks_data_scheme(self):
        """Блокировка data:// протокола."""
        with pytest.raises(URLValidationError, match="не разрешена"):
            validate_url("data:text/html,<script>alert(1)</script>")

    def test_blocks_javascript_scheme(self):
        """Блокировка javascript: протокола."""
        with pytest.raises(URLValidationError, match="не разрешена"):
            validate_url("javascript:alert(1)")

    def test_blocks_localhost(self):
        """Блокировка localhost."""
        with pytest.raises(URLValidationError, match="заблокирован"):
            validate_url("http://localhost:8080")

    def test_blocks_localhost_ip(self):
        """Блокировка 127.0.0.1."""
        with pytest.raises(URLValidationError, match="заблокирован"):
            validate_url("http://127.0.0.1:8080")

    def test_blocks_private_ip_192(self):
        """Блокировка 192.168.x.x."""
        with pytest.raises(URLValidationError):
            validate_url("http://192.168.1.1/admin")

    def test_blocks_private_ip_10(self):
        """Блокировка 10.x.x.x."""
        with pytest.raises(URLValidationError):
            validate_url("http://10.0.0.1/secrets")

    def test_blocks_private_ip_172(self):
        """Блокировка 172.16-31.x.x."""
        with pytest.raises(URLValidationError):
            validate_url("http://172.16.0.1/api")

    def test_blocks_link_local(self):
        """Блокировка 169.254.x.x (link-local / cloud metadata)."""
        with pytest.raises(URLValidationError):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_cloud_metadata(self):
        """Блокировка cloud metadata endpoints."""
        with pytest.raises(URLValidationError, match="заблокирован"):
            validate_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_local_domain(self):
        """Блокировка .local доменов."""
        with pytest.raises(URLValidationError, match="заблокирован"):
            validate_url("http://myserver.local:8080")

    def test_blocks_internal_domain(self):
        """Блокировка .internal доменов."""
        with pytest.raises(URLValidationError, match="заблокирован"):
            validate_url("http://api.internal/")

    def test_blocks_crlf_injection(self):
        """Блокировка CRLF инъекций."""
        with pytest.raises(URLValidationError, match="недопустимые символы"):
            validate_url("http://example.com\r\nX-Injected: true")

    def test_blocks_null_byte(self):
        """Блокировка null-byte инъекций."""
        with pytest.raises(URLValidationError, match="недопустимые символы"):
            validate_url("http://example.com\x00.jpg")

    def test_blocks_credentials_in_url(self):
        """Блокировка credentials в URL."""
        with pytest.raises(URLValidationError, match="credentials"):
            validate_url("http://user:pass@example.com/")

    def test_blocks_path_traversal(self):
        """Блокировка path traversal."""
        with pytest.raises(URLValidationError, match="traversal"):
            validate_url("http://example.com/../../../etc/passwd")

    def test_blocks_empty_url(self):
        """Блокировка пустого URL."""
        with pytest.raises(URLValidationError, match="пустым"):
            validate_url("")

    def test_blocks_missing_scheme(self):
        """Блокировка URL без схемы."""
        with pytest.raises(URLValidationError, match="схем"):
            validate_url("example.com")

    def test_blocks_too_long_url(self):
        """Блокировка слишком длинного URL."""
        long_url = "http://example.com/" + "a" * 3000
        with pytest.raises(URLValidationError, match="длинный"):
            validate_url(long_url)

    def test_blocks_invalid_port(self):
        """Блокировка невалидного порта."""
        with pytest.raises(URLValidationError, match="порт"):
            validate_url("http://example.com:99999/")

    def test_allows_valid_https(self):
        """Разрешить валидный HTTPS URL."""
        result = validate_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_allows_valid_http(self):
        """Разрешить валидный HTTP URL."""
        result = validate_url("http://example.com/page")
        assert "example.com" in result

    def test_allows_url_with_path(self):
        """Разрешить URL с путём."""
        result = validate_url("https://example.com/path/to/page?q=1")
        assert "example.com" in result

    def test_blocks_ipv6_loopback(self):
        """Блокировка IPv6 loopback ::1."""
        with pytest.raises(URLValidationError):
            validate_url("http://[::1]:8080/")


# ─── Rate Limiting Tests ───

class TestRateLimiting:
    """Тесты rate limiter."""

    def test_rate_limiter_allows_under_limit(self):
        """Token bucket пропускает запросы под лимитом."""
        from scripts.screenshot_service import _TokenBucket

        bucket = _TokenBucket(max_tokens=5, refill_rate=1.0)
        for _ in range(5):
            assert bucket.consume() is True

    def test_rate_limiter_blocks_over_limit(self):
        """Token bucket блокирует запросы сверх лимита."""
        from scripts.screenshot_service import _TokenBucket

        bucket = _TokenBucket(max_tokens=2, refill_rate=0.01)
        assert bucket.consume() is True
        assert bucket.consume() is True
        # Третий запрос должен быть заблокирован
        assert bucket.consume() is False

    def test_rate_limiter_refills_over_time(self):
        """Token bucket пополняется со временем."""
        import time

        from scripts.screenshot_service import _TokenBucket

        bucket = _TokenBucket(max_tokens=1, refill_rate=100.0)
        assert bucket.consume() is True
        assert bucket.consume() is False
        time.sleep(0.05)  # Подождать пополнения
        assert bucket.consume() is True


# ─── Cache Security Tests ───

class TestCacheSecurity:
    """Тесты безопасности кэша."""

    def test_cache_key_includes_format(self):
        """Ключ кэша зависит от формата."""
        from scripts.screenshot_service import cache_key

        key_png = cache_key("https://example.com", True, 1920, 1080, "png")
        key_pdf = cache_key("https://example.com", True, 1920, 1080, "pdf")
        assert key_png != key_pdf

    def test_cache_key_is_sha256(self):
        """Ключ кэша — SHA-256 хеш."""
        from scripts.screenshot_service import cache_key

        key = cache_key("https://example.com", False, 1920, 1080, "png")
        assert len(key) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

    def test_cache_key_deterministic(self):
        """Ключ кэша детерминистичен."""
        from scripts.screenshot_service import cache_key

        key1 = cache_key("https://example.com", True, 1920, 1080, "png")
        key2 = cache_key("https://example.com", True, 1920, 1080, "png")
        assert key1 == key2

    def test_get_cached_rejects_invalid_key(self):
        """get_cached_screenshot отклоняет невалидный ключ."""
        from scripts.screenshot_service import get_cached_screenshot

        result = get_cached_screenshot("../../../etc/passwd")
        assert result is None

    def test_get_cached_rejects_short_key(self):
        """get_cached_screenshot отклоняет короткий ключ."""
        from scripts.screenshot_service import get_cached_screenshot

        result = get_cached_screenshot("abc123")
        assert result is None


# ─── Input Validation Tests ───

class TestInputValidation:
    """Тесты валидации входных данных."""

    def test_screenshot_request_valid(self):
        """Валидный ScreenshotRequest создаётся."""
        from scripts.screenshot_service import ScreenshotRequest

        req = ScreenshotRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.full_page is False
        assert req.width == 1920
        assert req.height == 1080
        assert req.format == "png"

    def test_screenshot_request_rejects_invalid_url(self):
        """ScreenshotRequest отклоняет невалидный URL."""
        from scripts.screenshot_service import ScreenshotRequest

        with pytest.raises(Exception):
            ScreenshotRequest(url="file:///etc/passwd")

    def test_screenshot_request_rejects_xss_in_selector(self):
        """ScreenshotRequest отклоняет XSS в CSS селекторе."""
        from scripts.screenshot_service import ScreenshotRequest

        with pytest.raises(Exception):
            ScreenshotRequest(
                url="https://example.com",
                wait_for="<script>alert(1)</script>",
            )

    def test_screenshot_request_rejects_long_selector(self):
        """ScreenshotRequest отклоняет слишком длинный селектор."""
        from scripts.screenshot_service import ScreenshotRequest

        with pytest.raises(Exception):
            ScreenshotRequest(
                url="https://example.com",
                wait_for="div" * 300,
            )

    def test_screenshot_request_validates_viewport(self):
        """ScreenshotRequest валидирует размер viewport."""
        from scripts.screenshot_service import ScreenshotRequest

        # Слишком маленький
        with pytest.raises(Exception):
            ScreenshotRequest(url="https://example.com", width=100)

        # Слишком большой
        with pytest.raises(Exception):
            ScreenshotRequest(url="https://example.com", width=5000)
