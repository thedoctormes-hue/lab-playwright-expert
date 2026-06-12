"""
Тесты для Proxy Rotation модуля.

Покрытие:
- ProxyRotator: add_proxy, get_next, mark_failed, mark_success
- ProxyProtocol parsing
- Rotation strategies: round_robin, random
- Health check
- Statistics
- Edge cases
"""
import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lab_playwright_kit.proxy_rotation import (
    ProxyInfo,
    ProxyProtocol,
    ProxyRotator,
    RotationStrategy,
)


# ═══════════════════════════════════════════════════════════════════
# ProxyInfo
# ═══════════════════════════════════════════════════════════════════

class TestProxyInfo:
    """Тесты ProxyInfo dataclass."""

    def test_creation_basic(self):
        """Базовое создание ProxyInfo."""
        proxy = ProxyInfo(
            url="http://proxy1:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy1",
            port=8080,
        )
        assert proxy.url == "http://proxy1:8080"
        assert proxy.protocol == ProxyProtocol.HTTP
        assert proxy.host == "proxy1"
        assert proxy.port == 8080
        assert proxy.is_healthy is True
        assert proxy.failures == 0
        assert proxy.successes == 0

    def test_creation_with_auth(self):
        """Создание с аутентификацией."""
        proxy = ProxyInfo(
            url="http://user:pass@proxy1:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy1",
            port=8080,
            username="user",
            password="pass",
        )
        assert proxy.username == "user"
        assert proxy.password == "pass"

    def test_is_available_healthy(self):
        """Доступность здорового прокси."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        assert proxy.is_available is True

    def test_is_available_unhealthy_in_cooldown(self):
        """Недоступность нездорового прокси в cooldown."""
        import time

        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            is_healthy=False,
            cooldown_until=time.monotonic() + 300,
        )
        assert proxy.is_available is False

    def test_is_available_unhealthy_cooldown_expired(self):
        """Доступность после истечения cooldown."""
        import time

        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            is_healthy=False,
            failures=3,
            cooldown_until=time.monotonic() - 1,  # cooldown истёк
        )
        assert proxy.is_available is True
        # После проверки здоровье восстановлено
        assert proxy.is_healthy is True
        assert proxy.failures == 0

    def test_playwright_format_basic(self):
        """Формат для Playwright без аутентификации."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        fmt = proxy.playwright_format
        assert fmt == {"server": "http://proxy:8080"}

    def test_playwright_format_with_auth(self):
        """Формат для Playwright с аутентификацией."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            username="user",
            password="pass",
        )
        fmt = proxy.playwright_format
        assert fmt == {
            "server": "http://proxy:8080",
            "username": "user",
            "password": "pass",
        }

    def test_str_without_auth(self):
        """Строковое представление без аутентификации."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        assert str(proxy) == "http://proxy:8080"

    def test_str_with_auth(self):
        """Строковое представление с аутентификацией."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            username="user",
        )
        assert str(proxy) == "http://user@proxy:8080"


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — базовые операции
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorBasic:
    """Базовые тесты ProxyRotator."""

    def test_init_default(self):
        """Инициализация с дефолтными параметрами."""
        rotator = ProxyRotator()
        assert rotator._strategy == RotationStrategy.ROUND_ROBIN
        assert rotator.total_count == 0
        assert rotator.healthy_count == 0

    def test_init_random_strategy(self):
        """Инициализация с random стратегией."""
        rotator = ProxyRotator(strategy="random")
        assert rotator._strategy == RotationStrategy.RANDOM

    def test_add_proxy_http(self):
        """Добавление HTTP прокси."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy("http://proxy1:8080")
        assert rotator.total_count == 1
        assert proxy.protocol == ProxyProtocol.HTTP
        assert proxy.host == "proxy1"
        assert proxy.port == 8080

    def test_add_proxy_https(self):
        """Добавление HTTPS прокси."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy("https://proxy1:8443")
        assert proxy.protocol == ProxyProtocol.HTTPS
        assert proxy.port == 8443

    def test_add_proxy_socks5(self):
        """Добавление SOCKS5 прокси."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy("socks5://proxy1:1080")
        assert proxy.protocol == ProxyProtocol.SOCKS5
        assert proxy.port == 1080

    def test_add_proxy_with_auth(self):
        """Добавление прокси с аутентификацией."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy(
            "http://proxy1:8080",
            username="user",
            password="pass",
        )
        assert proxy.username == "user"
        assert proxy.password == "pass"

    def test_add_proxy_with_custom_params(self):
        """Добавление прокси с кастомными параметрами."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy(
            "http://proxy1:8080",
            weight=5,
            max_failures=10,
            cooldown_seconds=600,
        )
        assert proxy.weight == 5
        assert proxy.max_failures == 10
        assert proxy.cooldown_seconds == 600

    def test_add_multiple_proxies(self):
        """Добавление нескольких прокси."""
        rotator = ProxyRotator()
        rotator.add_proxy("http://proxy1:8080")
        rotator.add_proxy("http://proxy2:8080")
        rotator.add_proxy("socks5://proxy3:1080")
        assert rotator.total_count == 3

    def test_add_proxy_invalid_protocol(self):
        """Невалидный протокол — ValueError."""
        rotator = ProxyRotator()
        with pytest.raises(ValueError, match="Unsupported proxy protocol"):
            rotator.add_proxy("ftp://proxy1:21")

    def test_add_proxy_missing_port(self):
        """URL без порта — ValueError."""
        rotator = ProxyRotator()
        with pytest.raises(ValueError, match="must include port"):
            rotator.add_proxy("http://proxy1")

    def test_add_proxy_invalid_port(self):
        """Невалидный порт — ValueError."""
        rotator = ProxyRotator()
        with pytest.raises(ValueError, match="Port out of range"):
            rotator.add_proxy("http://proxy1:99999")


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — get_next и стратегии
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorGetNext:
    """Тесты get_next и стратегий ротации."""

    def test_get_next_empty_pool(self):
        """get_next при пустом пуле — None."""
        rotator = ProxyRotator()
        assert rotator.get_next() is None

    def test_get_next_single_proxy(self):
        """get_next с одним прокси."""
        rotator = ProxyRotator()
        proxy = rotator.add_proxy("http://proxy1:8080")
        result = rotator.get_next()
        assert result is proxy

    def test_round_robin_rotation(self):
        """Round-robin ротация по кругу."""
        rotator = ProxyRotator(strategy="round_robin")
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")
        p3 = rotator.add_proxy("http://proxy3:8080")

        assert rotator.get_next() is p1
        assert rotator.get_next() is p2
        assert rotator.get_next() is p3
        # Зацикливание
        assert rotator.get_next() is p1

    def test_random_strategy(self):
        """Random стратегия — возвращает один из прокси."""
        rotator = ProxyRotator(strategy="random")
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        # 100 раз — должны быть оба прокси (сравниваем по url)
        results = {rotator.get_next().url for _ in range(100)}
        assert p1.url in results
        assert p2.url in results

    def test_get_next_skips_unhealthy(self):
        """get_next пропускает нездоровые прокси."""
        rotator = ProxyRotator(strategy="round_robin")
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        # Пометить p1 как нездоровый
        p1.is_healthy = False
        p1.cooldown_until = float("inf")

        # Должен всегда возвращать p2
        for _ in range(5):
            assert rotator.get_next() is p2

    def test_get_next_all_unhealthy(self):
        """get_next когда все прокси нездоровы — None."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        p1.is_healthy = False
        p1.cooldown_until = float("inf")

        assert rotator.get_next() is None


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — mark_failed / mark_success
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorMarking:
    """Тесты mark_failed и mark_success."""

    def test_mark_failed_increments_counter(self):
        """mark_failed увеличивает счётчик неудач."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        proxy.failures = 0
        # Нужен rotator для вызова mark_failed
        rotator = ProxyRotator()
        rotator.add_proxy("http://proxy:8080")

        proxy.failures = 0
        proxy.failures += 1
        assert proxy.failures == 1

    def test_mark_failed_exceeds_max(self):
        """mark_failed при превышении max_failures — прокси исключается."""

        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
            max_failures=3,
        )

        # 3 неудачи
        for _ in range(3):
            proxy.failures += 1

        assert proxy.failures >= proxy.max_failures

    def test_mark_success_increments_counter(self):
        """mark_success увеличивает счётчик успехов."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        proxy.successes = 0
        proxy.successes += 1
        assert proxy.successes == 1

    def test_mark_success_resets_failures(self):
        """mark_success сбрасывает счётчик неудач."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        proxy.failures = 2
        proxy.failures = 0  # mark_success сбрасывает
        assert proxy.failures == 0

    def test_mark_success_updates_latency(self):
        """mark_success обновляет среднюю латентность."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        proxy.avg_latency_ms = 0.0
        # Первый успех
        latency = 100.0
        if proxy.avg_latency_ms == 0:
            proxy.avg_latency_ms = latency
        else:
            proxy.avg_latency_ms = 0.7 * proxy.avg_latency_ms + 0.3 * latency
        assert proxy.avg_latency_ms == 100.0

    def test_mark_success_moving_average(self):
        """mark_success использует скользящее среднее для латентности."""
        proxy = ProxyInfo(
            url="http://proxy:8080",
            protocol=ProxyProtocol.HTTP,
            host="proxy",
            port=8080,
        )
        proxy.avg_latency_ms = 100.0
        # Второй успех с другим latency
        new_latency = 200.0
        proxy.avg_latency_ms = 0.7 * proxy.avg_latency_ms + 0.3 * new_latency
        expected = 0.7 * 100.0 + 0.3 * 200.0  # = 130.0
        assert proxy.avg_latency_ms == pytest.approx(expected)


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — remove и reset
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorManagement:
    """Тесты управления пулом прокси."""

    def test_remove_proxy(self):
        """Удаление прокси из пула."""
        rotator = ProxyRotator()
        rotator.add_proxy("http://proxy1:8080")
        rotator.add_proxy("http://proxy2:8080")

        result = rotator.remove_proxy("http://proxy1:8080")
        assert result is True
        assert rotator.total_count == 1

    def test_remove_nonexistent_proxy(self):
        """Удаление несуществующего прокси."""
        rotator = ProxyRotator()
        rotator.add_proxy("http://proxy1:8080")

        result = rotator.remove_proxy("http://nonexistent:8080")
        assert result is False
        assert rotator.total_count == 1

    def test_reset_all_proxies(self):
        """Сброс всех прокси."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        # Испортить состояния
        p1.failures = 5
        p1.is_healthy = False
        p2.successes = 10

        rotator.reset()

        assert p1.failures == 0
        assert p1.is_healthy is True
        assert p2.successes == 0

    def test_healthy_count(self):
        """Подсчёт здоровых прокси."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        rotator.add_proxy("http://proxy2:8080")
        rotator.add_proxy("http://proxy3:8080")

        p1.is_healthy = False
        p1.cooldown_until = float("inf")

        assert rotator.healthy_count == 2
        assert rotator.unhealthy_count == 1

    def test_healthy_proxies_list(self):
        """Список здоровых прокси."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        p1.is_healthy = False
        p1.cooldown_until = float("inf")

        healthy = rotator.healthy_proxies
        assert len(healthy) == 1
        assert healthy[0] is p2


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — статистика
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorStats:
    """Тесты статистики пула прокси."""

    def test_get_stats_empty(self):
        """Статистика пустого пула."""
        rotator = ProxyRotator()
        stats = rotator.get_stats()

        assert stats["total"] == 0
        assert stats["healthy"] == 0
        assert stats["unhealthy"] == 0
        assert stats["total_successes"] == 0
        assert stats["total_failures"] == 0
        assert stats["avg_latency_ms"] == 0.0

    def test_get_stats_with_data(self):
        """Статистика с данными."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        p1.successes = 10
        p1.failures = 2
        p2.successes = 5
        p2.failures = 1

        stats = rotator.get_stats()
        assert stats["total"] == 2
        assert stats["total_successes"] == 15
        assert stats["total_failures"] == 3

    def test_get_stats_with_latency(self):
        """Статистика с латентностью."""
        rotator = ProxyRotator()
        p1 = rotator.add_proxy("http://proxy1:8080")
        p2 = rotator.add_proxy("http://proxy2:8080")

        p1.avg_latency_ms = 100.0
        p2.avg_latency_ms = 200.0

        stats = rotator.get_stats()
        assert stats["avg_latency_ms"] == 150.0


# ═══════════════════════════════════════════════════════════════════
# ProxyRotator — парсинг URL
# ═══════════════════════════════════════════════════════════════════

class TestProxyRotatorParsing:
    """Тесты парсинга URL прокси."""

    def test_parse_http_url(self):
        """Парсинг HTTP URL."""
        protocol = ProxyRotator._parse_protocol("http://proxy:8080")
        assert protocol == ProxyProtocol.HTTP

    def test_parse_https_url(self):
        """Парсинг HTTPS URL."""
        protocol = ProxyRotator._parse_protocol("https://proxy:8443")
        assert protocol == ProxyProtocol.HTTPS

    def test_parse_socks5_url(self):
        """Парсинг SOCKS5 URL."""
        protocol = ProxyRotator._parse_protocol("socks5://proxy:1080")
        assert protocol == ProxyProtocol.SOCKS5

    def test_parse_host_port(self):
        """Парсинг хоста и порта."""
        host, port = ProxyRotator._parse_host_port("http://proxy:8080")
        assert host == "proxy"
        assert port == 8080

    def test_parse_host_port_with_auth(self):
        """Парсинг хоста и порта с аутентификацией."""
        host, port = ProxyRotator._parse_host_port("http://user:pass@proxy:8080")
        assert host == "proxy"
        assert port == 8080

    def test_parse_host_port_with_path(self):
        """Парсинг хоста и порта с путём."""
        host, port = ProxyRotator._parse_host_port("http://proxy:8080/some/path")
        assert host == "proxy"
        assert port == 8080

    def test_parse_invalid_protocol(self):
        """Невалидный протокол — ValueError."""
        with pytest.raises(ValueError, match="Unsupported"):
            ProxyRotator._parse_protocol("ftp://proxy:21")

    def test_parse_missing_port(self):
        """Отсутствующий порт — ValueError."""
        with pytest.raises(ValueError, match="must include port"):
            ProxyRotator._parse_host_port("http://proxy")

    def test_parse_port_out_of_range(self):
        """Порт вне диапазона — ValueError."""
        with pytest.raises(ValueError, match="Port out of range"):
            ProxyRotator._parse_host_port("http://proxy:0")


# ═══════════════════════════════════════════════════════════════════
# ProxyProtocol enum
# ═══════════════════════════════════════════════════════════════════

class TestProxyProtocol:
    """Тесты ProxyProtocol enum."""

    def test_values(self):
        """Значения enum."""
        assert ProxyProtocol.HTTP.value == "http"
        assert ProxyProtocol.HTTPS.value == "https"
        assert ProxyProtocol.SOCKS5.value == "socks5"

    def test_from_string(self):
        """Создание из строки."""
        assert ProxyProtocol("http") == ProxyProtocol.HTTP
        assert ProxyProtocol("socks5") == ProxyProtocol.SOCKS5


# ═══════════════════════════════════════════════════════════════════
# RotationStrategy enum
# ═══════════════════════════════════════════════════════════════════

class TestRotationStrategy:
    """Тесты RotationStrategy enum."""

    def test_values(self):
        """Значения enum."""
        assert RotationStrategy.ROUND_ROBIN.value == "round_robin"
        assert RotationStrategy.RANDOM.value == "random"
