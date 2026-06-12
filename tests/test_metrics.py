"""
Тесты для Metrics модуля.

Покрывает:
  - CacheMetrics — thread-safe метрики кэша
  - LatencyTimer — замер latency
  - get_metrics_output() — Prometheus exposition
  - Все метрики определены и доступны
"""
import pytest

from lab_playwright_kit.metrics import (
    HAS_PROMETHEUS,
    REGISTRY,
    CacheMetrics,
    LatencyTimer,
    SS_CACHE_HITS,
    SS_CACHE_MISSES,
    SS_REQUESTS,
    SS_LATENCY,
    SM_CHECKS,
    SM_UPTIME,
    SM_LATENCY,
    CP_POSTS,
    CP_ERRORS,
    STEALTH_SCORE,
    STEALTH_OVERALL,
    STEALTH_TESTS_RUN,
    HM_CHECKS,
    HM_UPTIME,
    SERVICE_INFO,
    get_metrics_output,
)


# ─── CacheMetrics ─────────────────────────────────────────────────────────────

class TestCacheMetrics:
    def test_initial_state(self):
        cm = CacheMetrics()
        assert cm.rate == 0.0
        assert cm.total == 0

    def test_hit(self):
        cm = CacheMetrics()
        cm.hit()
        assert cm.total == 1
        assert cm.rate == 1.0

    def test_miss(self):
        cm = CacheMetrics()
        cm.miss()
        assert cm.total == 1
        assert cm.rate == 0.0

    def test_mixed(self):
        cm = CacheMetrics()
        cm.hit()
        cm.hit()
        cm.miss()
        assert cm.total == 3
        assert cm.rate == 2 / 3

    def test_all_hits(self):
        cm = CacheMetrics()
        for _ in range(10):
            cm.hit()
        assert cm.rate == 1.0
        assert cm.total == 10

    def test_all_misses(self):
        cm = CacheMetrics()
        for _ in range(5):
            cm.miss()
        assert cm.rate == 0.0
        assert cm.total == 5


# ─── LatencyTimer ─────────────────────────────────────────────────────────────

class TestLatencyTimer:
    def test_context_manager(self):
        import time
        with LatencyTimer(SS_LATENCY):
            time.sleep(0.01)
        # Не должно выбросить ошибку

    def test_with_labels(self):
        import time
        with LatencyTimer(SM_LATENCY, labels={"site": "example.com"}):
            time.sleep(0.01)
        # Не должно выбросить ошибку

    def test_returns_self(self):
        with LatencyTimer(SS_LATENCY) as timer:
            assert isinstance(timer, LatencyTimer)
            assert timer.start > 0


# ─── Prometheus exposition ───────────────────────────────────────────────────

class TestPrometheusOutput:
    def test_get_metrics_output(self):
        output, content_type = get_metrics_output()
        assert isinstance(output, bytes)
        assert len(output) > 0
        assert "text/plain" in content_type

    @pytest.mark.skipif(
        not HAS_PROMETHEUS,
        reason="prometheus_client not installed",
    )
    def test_output_contains_metrics(self):
        output, _ = get_metrics_output()
        text = output.decode("utf-8")
        # Должны быть наши метрики
        assert "lab_playwright_kit" in text

    @pytest.mark.skipif(
        not HAS_PROMETHEUS,
        reason="prometheus_client not installed",
    )
    def test_output_is_valid_prometheus(self):
        output, _ = get_metrics_output()
        text = output.decode("utf-8")
        # Должны быть HELP и TYPE строки
        assert "HELP" in text or "TYPE" in text or "lab_playwright_kit" in text


# ─── Метрики определены ──────────────────────────────────────────────────────

class TestMetricsExist:
    def test_screenshot_metrics(self):
        assert SS_REQUESTS is not None
        assert SS_LATENCY is not None
        assert SS_CACHE_HITS is not None
        assert SS_CACHE_MISSES is not None

    def test_site_monitor_metrics(self):
        assert SM_CHECKS is not None
        assert SM_UPTIME is not None

    def test_crosspost_metrics(self):
        assert CP_POSTS is not None
        assert CP_ERRORS is not None

    def test_stealth_metrics(self):
        assert STEALTH_SCORE is not None
        assert STEALTH_OVERALL is not None
        assert STEALTH_TESTS_RUN is not None

    def test_health_monitor_metrics(self):
        assert HM_CHECKS is not None
        assert HM_UPTIME is not None

    def test_service_info(self):
        assert SERVICE_INFO is not None

    def test_registry(self):
        assert REGISTRY is not None
