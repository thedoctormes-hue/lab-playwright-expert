"""
Lab Playwright Kit — система метрик.

Центральный реестр метрик для всех компонентов:
- screenshot-service: запросы, latency, cache, ошибки
- site_monitor: аптайм сайтов, load time, visual diff
- crosspost: успешность публикаций, время, ошибки
- stealth: stealth score по тестам

Формат: Prometheus-compatible (/metrics endpoint).
"""
from __future__ import annotations

import threading
import time

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


# ─── Fallback stubs при отсутствии prometheus_client ──────────────────────────

if not HAS_PROMETHEUS:
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

    class _NoOp:
        """No-op stub для метрик без prometheus_client."""
        def labels(self, **kwargs):
            return self
        def observe(self, value):
            pass
        def inc(self, amount=1):
            pass
        def dec(self, amount=1):
            pass
        def set(self, value):
            pass
        def info(self, data):
            pass

    class CollectorRegistry:
        pass

    def Counter(*_, **__):
        return _NoOp()

    def Gauge(*_, **__):
        return _NoOp()

    def Histogram(*_, **__):
        return _NoOp()

    def Info(*_, **__):
        return _NoOp()

    def generate_latest(registry=None):
        return b"# prometheus_client not installed\n"


# ─── Реестр ───────────────────────────────────────────────────────────────────

REGISTRY = CollectorRegistry()

# ─── Screenshot Service metrics ───────────────────────────────────────────────

SS_REQUESTS = Counter(
    "screenshot_requests_total",
    "Total screenshot requests",
    ["status", "format"],  # status: ok|error|cached; format: png|pdf
    registry=REGISTRY,
)

SS_LATENCY = Histogram(
    "screenshot_latency_seconds",
    "Screenshot generation latency",
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 18.0, 25.0, 35.0, 50.0),
    registry=REGISTRY,
)

SS_CACHE_HITS = Counter(
    "screenshot_cache_hits_total",
    "Cache hits",
    registry=REGISTRY,
)

SS_CACHE_MISSES = Counter(
    "screenshot_cache_misses_total",
    "Cache misses",
    registry=REGISTRY,
)

SS_ACTIVE_BROWSERS = Gauge(
    "screenshot_active_browsers",
    "Currently active browser instances",
    registry=REGISTRY,
)

SS_BROWSER_ERRORS = Counter(
    "screenshot_browser_errors_total",
    "Browser errors by type",
    ["error_type"],  # launch|navigation|timeout|screenshot
    registry=REGISTRY,
)

# ─── Site Monitor metrics ─────────────────────────────────────────────────────

SM_CHECKS = Counter(
    "site_monitor_checks_total",
    "Total site checks",
    ["site", "status"],  # status: ok|degraded|error
    registry=REGISTRY,
)

SM_LATENCY = Histogram(
    "site_monitor_check_latency_seconds",
    "Site check latency",
    ["site"],
    buckets=(1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0),
    registry=REGISTRY,
)

SM_UPTIME = Gauge(
    "site_monitor_uptime_ratio",
    "Site uptime ratio (0.0-1.0) over last 24h",
    ["site"],
    registry=REGISTRY,
)

SM_VISUAL_DIFF = Gauge(
    "site_monitor_visual_diff_ratio",
    "Visual diff ratio from baseline",
    ["site"],
    registry=REGISTRY,
)

SM_HTTP_STATUS = Gauge(
    "site_monitor_http_status_code",
    "Last HTTP status code",
    ["site"],
    registry=REGISTRY,
)

# ─── CrossPost metrics ────────────────────────────────────────────────────────

CP_POSTS = Counter(
    "crosspost_posts_total",
    "Total crosspost attempts",
    ["platform", "status"],  # status: success|error|auth_fail
    registry=REGISTRY,
)

CP_LATENCY = Histogram(
    "crosspost_latency_seconds",
    "Crosspost operation latency",
    ["platform"],
    buckets=(5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0),
    registry=REGISTRY,
)

CP_ERRORS = Counter(
    "crosspost_errors_total",
    "Crosspost errors by type",
    ["platform", "error_type"],  # error_type: auth|navigation|fill|publish|timeout
    registry=REGISTRY,
)

CP_COOKIES_AGE = Gauge(
    "crosspost_cookies_age_hours",
    "Age of stored cookies in hours",
    ["platform"],
    registry=REGISTRY,
)

# ─── Stealth metrics ──────────────────────────────────────────────────────────

STEALTH_SCORE = Gauge(
    "stealth_score_percent",
    "Stealth score (0-100) by test",
    ["test"],  # test: webdriver|headers|canvas|webgl|cloudflare
    registry=REGISTRY,
)

STEALTH_OVERALL = Gauge(
    "stealth_overall_score_percent",
    "Overall stealth score (0-100)",
    registry=REGISTRY,
)

STEALTH_TESTS_RUN = Counter(
    "stealth_tests_total",
    "Total stealth test runs",
    ["test", "result"],  # result: pass|fail
    registry=REGISTRY,
)

# ─── Health Monitor metrics ───────────────────────────────────────────────────

HM_CHECKS = Counter(
    "health_monitor_checks_total",
    "Health monitor checks",
    ["target", "status"],
    registry=REGISTRY,
)

HM_LATENCY = Histogram(
    "health_monitor_check_latency_seconds",
    "Health check latency",
    ["target"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

HM_UPTIME = Gauge(
    "health_monitor_uptime_percent",
    "Service uptime percentage (24h rolling)",
    ["target"],
    registry=REGISTRY,
)

# ─── Service info ─────────────────────────────────────────────────────────────

SERVICE_INFO = Info(
    "lab_playwright_kit",
    "Lab Playwright Kit build info",
    registry=REGISTRY,
)

SERVICE_INFO.info({"version": "0.2.0", "component": "lab-playwright-kit"})


# ─── Helper: cache hit rate ───────────────────────────────────────────────────

class CacheMetrics:
    """Thread-safe cache metrics tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def hit(self):
        with self._lock:
            self._hits += 1
        SS_CACHE_HITS.inc()

    def miss(self):
        with self._lock:
            self._misses += 1
        SS_CACHE_MISSES.inc()

    @property
    def rate(self) -> float:
        with self._lock:
            total = self._hits + self._misses
            if total == 0:
                return 0.0
            return self._hits / total

    @property
    def total(self) -> int:
        with self._lock:
            return self._hits + self._misses


# ─── Helper: latency timer ────────────────────────────────────────────────────

class LatencyTimer:
    """Контекстный менеджер для замера latency."""

    def __init__(self, histogram: Histogram, labels: dict | None = None):
        self.histogram = histogram
        self.labels = labels or {}
        self.start = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        elapsed = time.monotonic() - self.start
        if self.labels:
            self.histogram.labels(**self.labels).observe(elapsed)
        else:
            self.histogram.observe(elapsed)


# ─── Prometheus exposition ────────────────────────────────────────────────────

def get_metrics_output() -> tuple[bytes, str]:
    """Получить метрики в формате Prometheus."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
