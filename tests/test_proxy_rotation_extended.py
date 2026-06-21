"""
Расширенные тесты для ProxyInfo и ProxyRotator.

Покрывает:
  - ProxyInfo dataclass: все поля, значения по умолчанию
  - ProxyInfo.is_available property
  - ProxyInfo.playwright_format property
  - ProxyInfo.__str__
  - ProxyProtocol enum
  - RotationStrategy enum
  - ProxyRotator: add_proxy, get_next, mark_failed, mark_success
"""

from __future__ import annotations

import time

import pytest

from lab_playwright_kit.proxy_rotation import (
    ProxyInfo,
    ProxyProtocol,
    ProxyRotator,
    RotationStrategy,
)


# ─── ProxyProtocol enum ──────────────────────────────────────────────────


class TestProxyProtocol:
    def test_http(self):
        assert ProxyProtocol.HTTP.value == "http"

    def test_https(self):
        assert ProxyProtocol.HTTPS.value == "https"

    def test_socks5(self):
        assert ProxyProtocol.SOCKS5.value == "socks5"

    def test_str_enum(self):
        assert ProxyProtocol.HTTP == "http"
        assert ProxyProtocol.SOCKS5 == "socks5"


# ─── RotationStrategy enum ───────────────────────────────────────────────


class TestRotationStrategy:
    def test_round_robin(self):
        assert RotationStrategy.ROUND_ROBIN.value == "round_robin"

    def test_random(self):
        assert RotationStrategy.RANDOM.value == "random"


# ─── ProxyInfo defaults ──────────────────────────────────────────────────


class TestProxyInfoDefaults:
    def test_required_fields(self):
        pi = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        assert pi.url == "http://proxy:8080"
        assert pi.protocol == ProxyProtocol.HTTP
        assert pi.host == "proxy"
        assert pi.port == 8080

    def test_default_username_none(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.username is None

    def test_default_password_none(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.password is None

    def test_default_weight(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.weight == 1

    def test_default_max_failures(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.max_failures == 3

    def test_default_cooldown_seconds(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.cooldown_seconds == 300

    def test_default_failures(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.failures == 0

    def test_default_successes(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.successes == 0

    def test_default_is_healthy(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.is_healthy is True

    def test_default_avg_latency(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.avg_latency_ms == 0.0


# ─── ProxyInfo custom values ─────────────────────────────────────────────


class TestProxyInfoCustom:
    def test_with_auth(self):
        pi = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            username="user",
            password="pass",
        )
        assert pi.username == "user"
        assert pi.password == "pass"

    def test_socks5_protocol(self):
        pi = ProxyInfo(
            url="socks5://proxy:1080",
            protocol=ProxyProtocol.SOCKS5,
            host="proxy",
            port=1080,
        )
        assert pi.protocol == ProxyProtocol.SOCKS5

    def test_custom_weight(self):
        pi = ProxyInfo(
            url="http://p:8080",
            protocol=ProxyProtocol.HTTP,
            host="p",
            port=8080,
            weight=5,
        )
        assert pi.weight == 5

    def test_custom_max_failures(self):
        pi = ProxyInfo(
            url="http://p:8080",
            protocol=ProxyProtocol.HTTP,
            host="p",
            port=8080,
            max_failures=10,
        )
        assert pi.max_failures == 10


# ─── ProxyInfo.is_available ──────────────────────────────────────────────


class TestIsAvailable:
    def test_healthy_is_available(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert pi.is_available is True

    def test_unhealthy_in_cooldown(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        pi.is_healthy = False
        pi.cooldown_until = time.monotonic() + 300
        assert pi.is_available is False

    def test_unhealthy_cooldown_expired(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        pi.is_healthy = False
        pi.failures = 5
        pi.cooldown_until = time.monotonic() - 1  # expired
        assert pi.is_available is True
        assert pi.is_healthy is True
        assert pi.failures == 0


# ─── ProxyInfo.playwright_format ─────────────────────────────────────────


class TestPlaywrightFormat:
    def test_without_auth(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        fmt = pi.playwright_format
        assert fmt == {"server": "http://p:8080"}

    def test_with_auth(self):
        pi = ProxyInfo(
            url="http://p:8080",
            protocol=ProxyProtocol.HTTP,
            host="p",
            port=8080,
            username="user",
            password="pass",
        )
        fmt = pi.playwright_format
        assert fmt == {
            "server": "http://p:8080",
            "username": "user",
            "password": "pass",
        }


# ─── ProxyInfo.__str__ ───────────────────────────────────────────────────


class TestProxyInfoStr:
    def test_without_auth(self):
        pi = ProxyInfo(url="http://p:8080", protocol=ProxyProtocol.HTTP, host="p", port=8080)
        assert str(pi) == "http://p:8080"

    def test_with_auth(self):
        pi = ProxyInfo(
            url="http://p:8080",
            protocol=ProxyProtocol.HTTP,
            host="p",
            port=8080,
            username="user",
        )
        assert str(pi) == "http://user@p:8080"


# ─── ProxyRotator init ──────────────────────────────────────────────────


class TestProxyRotatorInit:
    def test_default_strategy(self):
        pr = ProxyRotator()
        assert pr._strategy == RotationStrategy.ROUND_ROBIN

    def test_random_strategy(self):
        pr = ProxyRotator(strategy="random")
        assert pr._strategy == RotationStrategy.RANDOM

    def test_empty_proxies(self):
        pr = ProxyRotator()
        assert pr._proxies == []

    def test_default_health_check_url(self):
        pr = ProxyRotator()
        assert pr._health_check_url == "https://httpbin.org/ip"


# ─── ProxyRotator.add_proxy ──────────────────────────────────────────────


class TestAddProxy:
    def test_add_http_proxy(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://proxy1:8080")
        assert pi.url == "http://proxy1:8080"
        assert pi.protocol == ProxyProtocol.HTTP
        assert pi.host == "proxy1"
        assert pi.port == 8080
        assert len(pr._proxies) == 1

    def test_add_socks5_proxy(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("socks5://proxy2:1080")
        assert pi.protocol == ProxyProtocol.SOCKS5
        assert pi.port == 1080

    def test_add_with_auth(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://proxy:8080", username="user", password="pass")
        assert pi.username == "user"
        assert pi.password == "pass"

    def test_add_multiple(self):
        pr = ProxyRotator()
        pr.add_proxy("http://p1:8080")
        pr.add_proxy("http://p2:8080")
        pr.add_proxy("socks5://p3:1080")
        assert len(pr._proxies) == 3

    def test_add_with_custom_params(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://p:8080", weight=5, max_failures=10, cooldown_seconds=600)
        assert pi.weight == 5
        assert pi.max_failures == 10
        assert pi.cooldown_seconds == 600

    def test_invalid_protocol_raises(self):
        pr = ProxyRotator()
        with pytest.raises(ValueError):
            pr.add_proxy("ftp://proxy:8080")


# ─── ProxyRotator.get_next ───────────────────────────────────────────────


class TestGetNext:
    def test_empty_returns_none(self):
        pr = ProxyRotator()
        assert pr.get_next() is None

    def test_round_robin(self):
        pr = ProxyRotator(strategy="round_robin")
        pr.add_proxy("http://p1:8080")
        pr.add_proxy("http://p2:8080")
        p1 = pr.get_next()
        p2 = pr.get_next()
        p3 = pr.get_next()
        assert p1.host == "p1"
        assert p2.host == "p2"
        assert p3.host == "p1"  # wraps around

    def test_random(self):
        pr = ProxyRotator(strategy="random")
        pr.add_proxy("http://p1:8080")
        pr.add_proxy("http://p2:8080")
        # Just verify it returns a proxy
        p = pr.get_next()
        assert p is not None

    def test_skips_unhealthy(self):
        pr = ProxyRotator()
        pr.add_proxy("http://p1:8080")
        pr.add_proxy("http://p2:8080")
        pr._proxies[0].is_healthy = False
        pr._proxies[0].cooldown_until = time.monotonic() + 300
        p = pr.get_next()
        assert p.host == "p2"


# ─── ProxyRotator.mark_failed / mark_success ─────────────────────────────


class TestMarkFailed:
    def test_increments_failures(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://p:8080")
        pr.mark_failed(pi)
        assert pi.failures == 1

    def test_exceeds_max_failures(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://p:8080", max_failures=2)
        pr.mark_failed(pi)
        pr.mark_failed(pi)
        assert pi.failures == 2
        assert pi.is_healthy is False

    def test_marks_cooldown(self):
        pr = ProxyRotator()
        pi = pr.add_proxy("http://p:8080", max_failures=1)
        pr.mark_failed(pi)
        assert pi.cooldown_until > 0
