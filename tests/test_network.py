"""
Тесты для Network Interceptor модуля.

Покрывает:
  - CapturedRequest — структура перехваченного запроса
  - NetworkLog — лог запросов и фильтрация
  - NetworkInterceptor — базовые проверки
"""
import pytest

from lab_playwright_kit.network import CapturedRequest, NetworkLog


# ─── CapturedRequest ─────────────────────────────────────────────────────────

class TestCapturedRequest:
    def test_create_basic(self):
        req = CapturedRequest(
            url="https://example.com/api",
            method="GET",
            headers={"Content-Type": "application/json"},
            post_data=None,
            resource_type="xhr",
        )
        assert req.url == "https://example.com/api"
        assert req.method == "GET"
        assert req.resource_type == "xhr"
        assert req.response_status is None
        assert req.response_body is None

    def test_create_with_response(self):
        req = CapturedRequest(
            url="https://example.com/api",
            method="POST",
            headers={},
            post_data='{"key": "value"}',
            resource_type="fetch",
            response_status=200,
            response_body='{"result": "ok"}',
        )
        assert req.response_status == 200
        assert req.response_body == '{"result": "ok"}'

    def test_default_values(self):
        req = CapturedRequest(
            url="https://example.com",
            method="GET",
            headers={},
            post_data=None,
            resource_type="document",
        )
        assert req.response_status is None
        assert req.response_body is None


# ─── NetworkLog ──────────────────────────────────────────────────────────────

class TestNetworkLog:
    def test_empty_log(self):
        log = NetworkLog()
        assert len(log.requests) == 0
        assert log.filter_by_domain("example.com") == []
        assert log.filter_by_type("xhr") == []
        assert log.filter_by_status(200) == []
        assert log.get_api_calls() == []

    def test_add_requests(self):
        log = NetworkLog()
        log.requests.append(CapturedRequest(
            url="https://example.com/api",
            method="GET",
            headers={},
            post_data=None,
            resource_type="xhr",
        ))
        log.requests.append(CapturedRequest(
            url="https://other.com/page",
            method="GET",
            headers={},
            post_data=None,
            resource_type="document",
        ))
        assert len(log.requests) == 2

    def test_filter_by_domain(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://example.com/api", method="GET", headers={}, post_data=None, resource_type="xhr"),
            CapturedRequest(url="https://other.com/page", method="GET", headers={}, post_data=None, resource_type="document"),
            CapturedRequest(url="https://example.com/other", method="POST", headers={}, post_data=None, resource_type="fetch"),
        ]
        filtered = log.filter_by_domain("example.com")
        assert len(filtered) == 2
        assert all("example.com" in r.url for r in filtered)

    def test_filter_by_type(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://a.com", method="GET", headers={}, post_data=None, resource_type="xhr"),
            CapturedRequest(url="https://b.com", method="GET", headers={}, post_data=None, resource_type="fetch"),
            CapturedRequest(url="https://c.com", method="GET", headers={}, post_data=None, resource_type="document"),
        ]
        assert len(log.filter_by_type("xhr")) == 1
        assert len(log.filter_by_type("fetch")) == 1
        assert len(log.filter_by_type("document")) == 1

    def test_filter_by_status(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://a.com", method="GET", headers={}, post_data=None, resource_type="xhr", response_status=200),
            CapturedRequest(url="https://b.com", method="GET", headers={}, post_data=None, resource_type="xhr", response_status=404),
            CapturedRequest(url="https://c.com", method="GET", headers={}, post_data=None, resource_type="xhr", response_status=500),
        ]
        assert len(log.filter_by_status(200)) == 1
        assert len(log.filter_by_status(404)) == 1
        assert len(log.filter_by_status(500)) == 1

    def test_get_api_calls(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://a.com/api", method="GET", headers={}, post_data=None, resource_type="xhr"),
            CapturedRequest(url="https://b.com/fetch", method="POST", headers={}, post_data=None, resource_type="fetch"),
            CapturedRequest(url="https://c.com/page", method="GET", headers={}, post_data=None, resource_type="document"),
            CapturedRequest(url="https://d.com/style.css", method="GET", headers={}, post_data=None, resource_type="stylesheet"),
        ]
        api_calls = log.get_api_calls()
        assert len(api_calls) == 2
        assert all(r.resource_type in ("xhr", "fetch") for r in api_calls)

    def test_to_dict(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://a.com/api", method="GET", headers={}, post_data=None, resource_type="xhr", response_status=200),
            CapturedRequest(url="https://b.com/page", method="GET", headers={}, post_data=None, resource_type="document", response_status=200),
        ]
        result = log.to_dict()
        assert result["total"] == 2
        assert len(result["requests"]) == 2
        assert result["requests"][0]["url"] == "https://a.com/api"
        assert result["requests"][0]["method"] == "GET"
        assert result["requests"][0]["status"] == 200
        assert result["requests"][0]["type"] == "xhr"

    def test_to_dict_empty(self):
        log = NetworkLog()
        result = log.to_dict()
        assert result["total"] == 0
        assert result["requests"] == []

    def test_filter_no_matches(self):
        log = NetworkLog()
        log.requests = [
            CapturedRequest(url="https://example.com/api", method="GET", headers={}, post_data=None, resource_type="xhr"),
        ]
        assert log.filter_by_domain("notexist.com") == []
        assert log.filter_by_type("stylesheet") == []
        assert log.filter_by_status(500) == []
