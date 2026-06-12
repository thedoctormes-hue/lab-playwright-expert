"""
Тесты для VPN Proxy Integration модуля.

Покрытие:
- VPNProxy: создание, свойства, форматы
- VPNProxyManager: get, get_by_country, get_random, list_all
- VPNProxyManager: from_yaml, health_check, get_healthy_proxy
- VPNProxyManager: __len__, __contains__, __repr__
- Edge cases: несуществующие прокси, пустой пул, невалидный YAML
"""
import os
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# Добавить src в sys.path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit.vpn_proxy import VPNProxy, VPNProxyManager


# ═══════════════════════════════════════════════════════════════════
# VPNProxy — базовые свойства
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyCreation:
    """Тесты создания VPNProxy."""

    def test_create_socks5_proxy(self):
        """Создание SOCKS5 прокси."""
        proxy = VPNProxy(
            name="poland",
            server="socks5://127.0.0.1:10808",
            country="PL",
            exit_ip="78.17.43.205",
        )
        assert proxy.name == "poland"
        assert proxy.server == "socks5://127.0.0.1:10808"
        assert proxy.country == "PL"
        assert proxy.exit_ip == "78.17.43.205"
        assert proxy.protocol == "VLESS+REALITY"
        assert proxy.is_direct is False

    def test_create_direct_proxy(self):
        """Создание прямого подключения (без прокси)."""
        proxy = VPNProxy(
            name="direct",
            server=None,
            country="DIRECT",
            exit_ip="89.169.4.51",
            protocol="DIRECT",
        )
        assert proxy.is_direct is True
        assert proxy.server is None

    def test_create_with_description(self):
        """Создание с описанием."""
        proxy = VPNProxy(
            name="florida",
            server="socks5://127.0.0.1:63567",
            country="US",
            exit_ip="104.253.1.210",
            description="Florida server",
        )
        assert proxy.description == "Florida server"

    def test_default_protocol(self):
        """Протокол по умолчанию — VLESS+REALITY."""
        proxy = VPNProxy(
            name="test",
            server="socks5://127.0.0.1:1080",
            country="XX",
            exit_ip="1.2.3.4",
        )
        assert proxy.protocol == "VLESS+REALITY"


class TestVPNProxyHostPort:
    """Тесты парсинга host:port."""

    def test_socks5_host_port(self):
        """Парсинг SOCKS5 URL."""
        proxy = VPNProxy(
            name="poland",
            server="socks5://127.0.0.1:10808",
            country="PL",
            exit_ip="78.17.43.205",
        )
        assert proxy.host_port == ("127.0.0.1", 10808)

    def test_direct_host_port_is_none(self):
        """host_port для direct — None."""
        proxy = VPNProxy(
            name="direct",
            server=None,
            country="DIRECT",
            exit_ip="89.169.4.51",
        )
        assert proxy.host_port is None

    def test_http_host_port(self):
        """Парсинг HTTP URL."""
        proxy = VPNProxy(
            name="http_proxy",
            server="http://proxy.example.com:8080",
            country="US",
            exit_ip="1.2.3.4",
        )
        assert proxy.host_port == ("proxy.example.com", 8080)

    def test_host_port_with_auth(self):
        """Парсинг URL с аутентификацией."""
        proxy = VPNProxy(
            name="auth_proxy",
            server="socks5://user:pass@127.0.0.1:1080",
            country="XX",
            exit_ip="1.2.3.4",
        )
        assert proxy.host_port == ("127.0.0.1", 1080)


class TestVPNProxyPlaywrightFormat:
    """Тесты формата для Playwright."""

    def test_socks5_playwright_format(self):
        """Формат Playwright для SOCKS5."""
        proxy = VPNProxy(
            name="poland",
            server="socks5://127.0.0.1:10808",
            country="PL",
            exit_ip="78.17.43.205",
        )
        fmt = proxy.to_playwright_format()
        assert fmt == {"server": "socks5://127.0.0.1:10808"}

    def test_direct_playwright_format_is_none(self):
        """Формат Playwright для direct — None."""
        proxy = VPNProxy(
            name="direct",
            server=None,
            country="DIRECT",
            exit_ip="89.169.4.51",
        )
        assert proxy.to_playwright_format() is None


class TestVPNProxyStr:
    """Тесты строкового представления."""

    def test_str_socks5(self):
        """Строка для SOCKS5 прокси."""
        proxy = VPNProxy(
            name="poland",
            server="socks5://127.0.0.1:10808",
            country="PL",
            exit_ip="78.17.43.205",
        )
        s = str(proxy)
        assert "poland" in s
        assert "socks5://127.0.0.1:10808" in s
        assert "PL" in s

    def test_str_direct(self):
        """Строка для direct."""
        proxy = VPNProxy(
            name="direct",
            server=None,
            country="DIRECT",
            exit_ip="89.169.4.51",
        )
        s = str(proxy)
        assert "direct" in s
        assert "DIRECT" in s


# ═══════════════════════════════════════════════════════════════════
# VPNProxyManager — инициализация и базовые методы
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyManagerInit:
    """Тесты инициализации VPNProxyManager."""

    def test_default_proxies(self):
        """Дефолтные прокси загружаются автоматически."""
        mgr = VPNProxyManager()
        assert len(mgr) == 3
        assert "poland" in mgr
        assert "florida" in mgr
        assert "direct" in mgr

    def test_custom_proxies(self):
        """Загрузка кастомных прокси."""
        custom = [
            {
                "name": "custom1",
                "server": "socks5://10.0.0.1:1080",
                "country": "DE",
                "exit_ip": "10.0.0.1",
            },
        ]
        mgr = VPNProxyManager(proxies=custom)
        assert len(mgr) == 1
        assert "custom1" in mgr

    def test_empty_proxies(self):
        """Пустой список прокси."""
        mgr = VPNProxyManager(proxies=[])
        assert len(mgr) == 0

    def test_repr(self):
        """Строковое представление менеджера."""
        mgr = VPNProxyManager()
        r = repr(mgr)
        assert "VPNProxyManager" in r
        assert "poland" in r


class TestVPNProxyManagerGet:
    """Тесты получения прокси."""

    def test_get_by_name(self):
        """Получение прокси по имени."""
        mgr = VPNProxyManager()
        proxy = mgr.get("poland")
        assert proxy is not None
        assert proxy.name == "poland"
        assert proxy.country == "PL"

    def test_get_nonexistent(self):
        """Получение несуществующего прокси — None."""
        mgr = VPNProxyManager()
        assert mgr.get("nonexistent") is None

    def test_get_by_country_pl(self):
        """Получение по коду страны PL."""
        mgr = VPNProxyManager()
        proxy = mgr.get_by_country("PL")
        assert proxy is not None
        assert proxy.name == "poland"

    def test_get_by_country_us(self):
        """Получение по коду страны US."""
        mgr = VPNProxyManager()
        proxy = mgr.get_by_country("US")
        assert proxy is not None
        assert proxy.name == "florida"

    def test_get_by_country_direct(self):
        """Получение по коду страны DIRECT."""
        mgr = VPNProxyManager()
        proxy = mgr.get_by_country("DIRECT")
        assert proxy is not None
        assert proxy.name == "direct"

    def test_get_by_country_nonexistent(self):
        """Получение по несуществующей стране — None."""
        mgr = VPNProxyManager()
        assert mgr.get_by_country("XX") is None

    def test_get_by_country_case_insensitive(self):
        """Поиск страны регистронезависимый."""
        mgr = VPNProxyManager()
        assert mgr.get_by_country("pl") is not None
        assert mgr.get_by_country("PL") is not None
        assert mgr.get_by_country("Pl") is not None

    def test_get_random(self):
        """Случайный прокси — не direct."""
        mgr = VPNProxyManager()
        for _ in range(20):
            proxy = mgr.get_random()
            assert proxy is not None
            assert proxy.is_direct is False

    def test_get_random_only_direct_available(self):
        """get_random когда доступен только direct — None."""
        mgr = VPNProxyManager(proxies=[
            {"name": "direct", "server": None, "country": "DIRECT", "exit_ip": "1.2.3.4"},
        ])
        assert mgr.get_random() is None

    def test_list_all(self):
        """Список всех прокси."""
        mgr = VPNProxyManager()
        proxies = mgr.list_all()
        assert len(proxies) == 3
        names = {p.name for p in proxies}
        assert names == {"poland", "florida", "direct"}


# ═══════════════════════════════════════════════════════════════════
# VPNProxyManager — from_yaml
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyManagerFromYaml:
    """Тесты загрузки из YAML."""

    def test_from_yaml_valid(self, tmp_path):
        """Загрузка валидного YAML."""
        config = {
            "proxies": [
                {
                    "name": "test_proxy",
                    "server": "socks5://10.0.0.1:1080",
                    "country": "DE",
                    "exit_ip": "10.0.0.1",
                    "protocol": "VLESS+REALITY",
                },
            ],
        }
        yaml_path = tmp_path / "test_proxies.yaml"
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")

        mgr = VPNProxyManager.from_yaml(yaml_path)
        assert len(mgr) == 1
        proxy = mgr.get("test_proxy")
        assert proxy is not None
        assert proxy.country == "DE"

    def test_from_yaml_file_not_found(self):
        """FileNotFoundError для несуществующего файла."""
        with pytest.raises(FileNotFoundError):
            VPNProxyManager.from_yaml("/nonexistent/path/proxies.yaml")

    def test_from_yaml_missing_proxies_key(self, tmp_path):
        """KeyError для файла без ключа 'proxies'."""
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text(yaml.dump({"not_proxies": []}), encoding="utf-8")

        with pytest.raises(KeyError, match="proxies"):
            VPNProxyManager.from_yaml(yaml_path)

    def test_from_yaml_string_path(self, tmp_path):
        """from_yaml принимает строковый путь."""
        config = {
            "proxies": [
                {
                    "name": "p1",
                    "server": "socks5://127.0.0.1:1080",
                    "country": "XX",
                    "exit_ip": "1.2.3.4",
                },
            ],
        }
        yaml_path = tmp_path / "proxies.yaml"
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")

        mgr = VPNProxyManager.from_yaml(str(yaml_path))
        assert len(mgr) == 1

    def test_from_yaml_with_defaults(self, tmp_path):
        """YAML с минимальными полями — дефолты подставляются."""
        config = {
            "proxies": [
                {
                    "name": "minimal",
                    "server": "socks5://127.0.0.1:1080",
                    "country": "XX",
                    "exit_ip": "1.2.3.4",
                },
            ],
        }
        yaml_path = tmp_path / "minimal.yaml"
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")

        mgr = VPNProxyManager.from_yaml(yaml_path)
        proxy = mgr.get("minimal")
        assert proxy.protocol == "VLESS+REALITY"
        assert proxy.description == ""


# ═══════════════════════════════════════════════════════════════════
# VPNProxyManager — health_check
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyManagerHealthCheck:
    """Тесты health check."""

    def test_health_check_direct_always_true(self):
        """Direct прокси всегда здоров."""
        proxy = VPNProxy(
            name="direct",
            server=None,
            country="DIRECT",
            exit_ip="89.169.4.51",
        )
        assert VPNProxyManager.health_check(proxy) is True

    def test_health_check_unreachable_proxy(self):
        """Недоступный прокси — False."""
        proxy = VPNProxy(
            name="unreachable",
            server="socks5://127.0.0.1:1",  # порт 1 — закрыт
            country="XX",
            exit_ip="1.2.3.4",
        )
        assert VPNProxyManager.health_check(proxy, timeout=1.0) is False

    def test_health_check_with_open_port(self):
        """Прокси с открытым портом — True."""
        # Создать временный TCP-сервер
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        try:
            proxy = VPNProxy(
                name="local",
                server=f"socks5://127.0.0.1:{port}",
                country="XX",
                exit_ip="127.0.0.1",
            )
            assert VPNProxyManager.health_check(proxy, timeout=2.0) is True
        finally:
            server.close()

    def test_health_check_invalid_server_url(self):
        """health_check с невалидным URL — False."""
        proxy = VPNProxy(
            name="bad",
            server="not-a-url",
            country="XX",
            exit_ip="1.2.3.4",
        )
        # host_port вернёт None для невалидного URL
        assert VPNProxyManager.health_check(proxy) is False


class TestVPNProxyManagerGetHealthyProxy:
    """Тесты get_healthy_proxy."""

    def test_get_healthy_proxy_prefer(self):
        """get_healthy_proxy с предпочтением."""
        # Все прокси недоступные, кроме direct
        mgr = VPNProxyManager()
        # Все прокси недоступны — fallback на direct
        result = mgr.get_healthy_proxy(prefer="poland")
        # Должен вернуть direct как fallback
        assert result is not None
        assert result.name == "direct"

    def test_get_healthy_proxy_fallback_to_direct(self):
        """Fallback на direct когда все VPN прокси недоступны."""
        mgr = VPNProxyManager()
        result = mgr.get_healthy_proxy()
        # direct всегда здоров
        assert result is not None
        assert result.name == "direct"

    def test_get_healthy_proxy_no_direct(self):
        """get_healthy_proxy без direct в конфиге."""
        mgr = VPNProxyManager(proxies=[
            {
                "name": "p1",
                "server": "socks5://127.0.0.1:1",
                "country": "XX",
                "exit_ip": "1.2.3.4",
            },
        ])
        # p1 недоступен, direct нет — None
        result = mgr.get_healthy_proxy()
        assert result is None

    def test_get_healthy_proxy_empty_pool(self):
        """get_healthy_proxy с пустым пулом."""
        mgr = VPNProxyManager(proxies=[])
        assert mgr.get_healthy_proxy() is None


# ═══════════════════════════════════════════════════════════════════
# VPNProxyManager — dunder methods
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyManagerDunder:
    """Тесты dunder методов."""

    def test_len(self):
        """len() возвращает количество прокси."""
        mgr = VPNProxyManager()
        assert len(mgr) == 3

    def test_contains_existing(self):
        """in для существующего прокси."""
        mgr = VPNProxyManager()
        assert "poland" in mgr
        assert "florida" in mgr
        assert "direct" in mgr

    def test_contains_nonexisting(self):
        """in для несуществующего прокси."""
        mgr = VPNProxyManager()
        assert "nonexistent" not in mgr

    def test_len_empty(self):
        """len() для пустого пула."""
        mgr = VPNProxyManager(proxies=[])
        assert len(mgr) == 0


# ═══════════════════════════════════════════════════════════════════
# VPNProxyManager — PROXIES class attribute
# ═══════════════════════════════════════════════════════════════════

class TestVPNProxyManagerDefaults:
    """Тесты дефолтных прокси."""

    def test_default_proxies_count(self):
        """3 дефолтных прокси."""
        assert len(VPNProxyManager.PROXIES) == 3

    def test_default_proxies_have_required_fields(self):
        """Все дефолтные прокси имеют обязательные поля."""
        required = {"name", "server", "country", "exit_ip"}
        for p in VPNProxyManager.PROXIES:
            assert required.issubset(p.keys()), f"Missing fields in {p.get('name', '?')}"

    def test_default_proxies_names(self):
        """Имена дефолтных прокси."""
        names = {p["name"] for p in VPNProxyManager.PROXIES}
        assert names == {"poland", "florida", "direct"}

    def test_poland_details(self):
        """Детали Poland прокси."""
        poland = next(p for p in VPNProxyManager.PROXIES if p["name"] == "poland")
        assert poland["server"] == "socks5://127.0.0.1:10808"
        assert poland["country"] == "PL"
        assert poland["exit_ip"] == "78.17.43.205"
        assert poland["protocol"] == "VLESS+REALITY"

    def test_florida_details(self):
        """Детали Florida прокси."""
        florida = next(p for p in VPNProxyManager.PROXIES if p["name"] == "florida")
        assert florida["server"] == "socks5://127.0.0.1:63567"
        assert florida["country"] == "US"
        assert florida["exit_ip"] == "104.253.1.210"

    def test_direct_details(self):
        """Детали Direct прокси."""
        direct = next(p for p in VPNProxyManager.PROXIES if p["name"] == "direct")
        assert direct["server"] is None
        assert direct["country"] == "DIRECT"
        assert direct["exit_ip"] == "89.169.4.51"
