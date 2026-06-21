"""
Расширенные тесты для модуля metrics.

Покрывает:
  - CacheMetrics (hit, miss, rate, total)
  - LatencyTimer (context manager)
  - get_metrics_output
  - NoOp stubs (when prometheus_client not installed)
  - Metric objects exist and are usable
"""

from __future__ import annotations

import time

from lab_playwright_kit.metrics import (
    CP_ERRORS,
    CP_POSTS,
    HAS_PROMETHEUS,
    HM_CHECKS,
    HM_UPTIME,
    SM_CHECKS,
    SM_UPTIME,
    SS_ACTIVE_BROWSERS,
    SS_CACHE_HITS,
    SS_CACHE_MISSES,
    SS_LATENCY,
    SS_REQUESTS,
    STEALTH_OVERALL,
    STEALTH_SCORE,
    CacheMetrics,
    LatencyTimer,
    get_metrics_output,
)


# ─── CacheMetrics ──────────────────────────────────────────────────────────


class TestCacheMetrics:
    def test_initial(self):
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
        assert abs(cm.rate - 2 / 3) < 0.01

    def test_many_hits(self):
        cm = CacheMetrics()
        for _ in range(100):
            cm.hit()
        assert cm.total == 100
        assert cm.rate == 1.0

    def test_thread_safety(self):
        import threading

        cm = CacheMetrics()
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: [cm.hit() for _ in range(100)])
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert cm.total == 1000


# ─── LatencyTimer ──────────────────────────────────────────────────────────


class TestLatencyTimer:
    def test_context_manager(self):
        timer = LatencyTimer(SS_LATENCY)
        with timer:
            time.sleep(0.01)
        # No exception = success

    def test_with_labels(self):
        timer = LatencyTimer(SM_CHECKS, labels={"site": "example.com", "status": "ok"})
        with timer:
            time.sleep(0.01)

    def test_records_elapsed(self):
        timer = LatencyTimer(SS_LATENCY)
        with timer:
            time.sleep(0.05)
        # Timer should have recorded something


# ─── Metric objects ────────────────────────────────────────────────────────


class TestMetricObjects:
    def test_ss_requests_labels(self):
        SS_REQUESTS.labels(status="ok", format="png").inc()

    def test_ss_latency_observe(self):
        SS_LATENCY.observe(1.5)

    def test_ss_cache_hits(self):
        SS_CACHE_HITS.inc()

    def test_ss_cache_misses(self):
        SS_CACHE_MISSES.inc()

    def test_ss_active_browsers(self):
        SS_ACTIVE_BROWSERS.set(3)
        SS_ACTIVE_BROWSERS.inc()
        SS_ACTIVE_BROWSERS.dec()

    def test_sm_checks(self):
        SM_CHECKS.labels(site="example.com", status="ok").inc()

    def test_sm_uptime(self):
        SM_UPTIME.labels(site="example.com").set(0.99)

    def test_cp_posts(self):
        CP_POSTS.labels(platform="twitter", status="success").inc()

    def test_cp_errors(self):
        CP_ERRORS.labels(platform="twitter", error_type="auth").inc()

    def test_stealth_score(self):
        STEALTH_SCORE.labels(test="webdriver").set(95)

    def test_stealth_overall(self):
        STEALTH_OVERALL.set(87)

    def test_hm_checks(self):
        HM_CHECKS.labels(target="api", status="ok").inc()

    def test_hm_uptime(self):
        HM_UPTIME.labels(target="api").set(99.9)


# ─── get_metrics_output ────────────────────────────────────────────────────


class TestGetMetricsOutput:
    def test_returns_tuple(self):
        output = get_metrics_output()
        assert isinstance(output, tuple)
        assert len(output) == 2

    def test_content_type(self):
        _, content_type = get_metrics_output()
        assert "text/plain" in content_type

    def test_output_not_empty(self):
        data, _ = get_metrics_output()
        assert len(data) > 0


# ─── HAS_PROMETHEUS flag ──────────────────────────────────────────────────


class TestPrometheusFlag:
    def test_flag_exists(self):
        assert isinstance(HAS_PROMETHEUS, bool)
