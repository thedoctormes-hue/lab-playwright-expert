"""
Alert Manager — система алертов для Playwright-инфраструктуры.

Правила алертов с пороговыми значениями:
- CRITICAL: сервис down, сайт недоступен > 5 мин
- WARNING: деградация, latency > порога, stealth score < 70%
- INFO: кэш hit rate < 50%, куки протухают

Формат совместим с Prometheus Alertmanager (alerts.yml).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from loguru import logger


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """Правило алерта."""
    name: str
    description: str
    severity: Severity
    # Условие: выражение, которое вычисляется из метрик
    condition: str  # человекочитаемое описание
    # Пороговые значения
    threshold_warning: float
    threshold_critical: float
    # Длительность перед срабатыванием (секунды)
    duration: int = 0
    # Группировка
    group: str = "playwright"


@dataclass
class Alert:
    """Сработавший алерт."""
    rule_name: str
    severity: Severity
    message: str
    timestamp: str
    value: float
    threshold: float
    group: str
    resolved: bool = False
    resolved_at: str | None = None


# ─── Пороговые значения ───────────────────────────────────────────────────────

# Screenshot Service
# Latency: p95 < 8s (warning), p95 > 15s (critical)
# Error rate: < 5% (ok), 5-15% (warning), > 15% (critical)
# Cache hit rate: > 60% (ok), 40-60% (warning), < 40% (critical)
# Active browsers: < 5 (ok), 5-10 (warning), > 10 (critical)

# Site Monitor
# Uptime: > 99% (ok), 95-99% (warning), < 95% (critical)
# Load time: < 5s (ok), 5-15s (warning), > 15s (critical)
# Visual diff: < 10% (ok), 10-25% (warning), > 25% (critical)

# CrossPost
# Success rate: > 90% (ok), 70-90% (warning), < 70% (critical)
# Cookies age: < 72h (ok), 72-120h (warning), > 120h (critical)

# Stealth
# Score: > 80% (ok), 60-80% (warning), < 60% (critical)

# Health Monitor
# Uptime: > 99.5% (ok), 98-99.5% (warning), < 98% (critical)
# Response time: < 2s (ok), 2-5s (warning), > 5s (critical)


# ─── Правила ──────────────────────────────────────────────────────────────────

ALERT_RULES = [
    # === Screenshot Service ===
    AlertRule(
        name="ScreenshotHighLatency",
        description="Screenshot p95 latency > threshold",
        severity=Severity.WARNING,
        condition="screenshot_latency_seconds:p95 > threshold",
        threshold_warning=8.0,
        threshold_critical=15.0,
        duration=120,
        group="screenshot-service",
    ),
    AlertRule(
        name="ScreenshotCriticalLatency",
        description="Screenshot p95 latency critical",
        severity=Severity.CRITICAL,
        condition="screenshot_latency_seconds:p95 > threshold",
        threshold_warning=15.0,
        threshold_critical=25.0,
        duration=60,
        group="screenshot-service",
    ),
    AlertRule(
        name="ScreenshotHighErrorRate",
        description="Screenshot error rate > threshold",
        severity=Severity.WARNING,
        condition="screenshot_requests_total:error_rate > threshold",
        threshold_warning=0.05,
        threshold_critical=0.15,
        duration=180,
        group="screenshot-service",
    ),
    AlertRule(
        name="ScreenshotLowCacheHitRate",
        description="Cache hit rate < threshold",
        severity=Severity.WARNING,
        condition="screenshot_cache_hit_rate < threshold",
        threshold_warning=0.50,
        threshold_critical=0.30,
        duration=300,
        group="screenshot-service",
    ),
    AlertRule(
        name="ScreenshotTooManyBrowsers",
        description="Too many concurrent browser instances",
        severity=Severity.WARNING,
        condition="screenshot_active_browsers > threshold",
        threshold_warning=5.0,
        threshold_critical=10.0,
        duration=60,
        group="screenshot-service",
    ),
    AlertRule(
        name="ScreenshotBrowserLaunchErrors",
        description="Browser launch errors detected",
        severity=Severity.CRITICAL,
        condition="screenshot_browser_errors_total:error_type=launch > threshold",
        threshold_warning=3.0,
        threshold_critical=10.0,
        duration=60,
        group="screenshot-service",
    ),

    # === Site Monitor ===
    AlertRule(
        name="SiteDown",
        description="Site is down (HTTP 4xx/5xx or connection error)",
        severity=Severity.CRITICAL,
        condition="site_monitor_checks_total:status=error > threshold",
        threshold_warning=0.0,
        threshold_critical=3.0,  # 3 consecutive errors
        duration=0,
        group="site-monitor",
    ),
    AlertRule(
        name="SiteDegraded",
        description="Site degraded (title mismatch, selector missing)",
        severity=Severity.WARNING,
        condition="site_monitor_checks_total:status=degraded > threshold",
        threshold_warning=2.0,
        threshold_critical=5.0,
        duration=300,
        group="site-monitor",
    ),
    AlertRule(
        name="SiteHighLoadTime",
        description="Site load time > threshold",
        severity=Severity.WARNING,
        condition="site_monitor_check_latency_seconds:p95 > threshold",
        threshold_warning=5.0,
        threshold_critical=15.0,
        duration=180,
        group="site-monitor",
    ),
    AlertRule(
        name="SiteLowUptime",
        description="Site uptime < threshold",
        severity=Severity.WARNING,
        condition="site_monitor_uptime_ratio < threshold",
        threshold_warning=0.99,
        threshold_critical=0.95,
        duration=600,
        group="site-monitor",
    ),
    AlertRule(
        name="SiteVisualRegression",
        description="Visual regression detected",
        severity=Severity.WARNING,
        condition="site_monitor_visual_diff_ratio > threshold",
        threshold_warning=0.10,
        threshold_critical=0.25,
        duration=0,
        group="site-monitor",
    ),

    # === CrossPost ===
    AlertRule(
        name="CrossPostHighFailureRate",
        description="Crosspost failure rate > threshold",
        severity=Severity.WARNING,
        condition="crosspost_posts_total:failure_rate > threshold",
        threshold_warning=0.10,
        threshold_critical=0.30,
        duration=0,
        group="crosspost",
    ),
    AlertRule(
        name="CrossPostAuthFailure",
        description="Crosspost authentication failure",
        severity=Severity.CRITICAL,
        condition="crosspost_errors_total:error_type=auth > threshold",
        threshold_warning=0.0,
        threshold_critical=1.0,
        duration=0,
        group="crosspost",
    ),
    AlertRule(
        name="CrossPostCookiesExpiring",
        description="Crosspost cookies expiring soon",
        severity=Severity.WARNING,
        condition="crosspost_cookies_age_hours > threshold",
        threshold_warning=72.0,
        threshold_critical=120.0,
        duration=0,
        group="crosspost",
    ),

    # === Stealth ===
    AlertRule(
        name="StealthScoreLow",
        description="Stealth score < threshold",
        severity=Severity.WARNING,
        condition="stealth_overall_score_percent < threshold",
        threshold_warning=80.0,
        threshold_critical=60.0,
        duration=0,
        group="stealth",
    ),
    AlertRule(
        name="StealthWebdriverDetected",
        description="Webdriver detected by anti-bot systems",
        severity=Severity.CRITICAL,
        condition="stealth_score_percent:test=webdriver < threshold",
        threshold_warning=100.0,
        threshold_critical=100.0,  # Any detection = critical
        duration=0,
        group="stealth",
    ),

    # === Health Monitor ===
    AlertRule(
        name="ServiceDown",
        description="Service is down (health check failing)",
        severity=Severity.CRITICAL,
        condition="health_monitor_checks_total:status=down > threshold",
        threshold_warning=0.0,
        threshold_critical=2.0,  # 2 consecutive failures
        duration=0,
        group="health-monitor",
    ),
    AlertRule(
        name="ServiceDegraded",
        description="Service degraded",
        severity=Severity.WARNING,
        condition="health_monitor_checks_total:status=degraded > threshold",
        threshold_warning=3.0,
        threshold_critical=5.0,
        duration=120,
        group="health-monitor",
    ),
    AlertRule(
        name="ServiceLowUptime",
        description="Service uptime < threshold",
        severity=Severity.WARNING,
        condition="health_monitor_uptime_percent < threshold",
        threshold_warning=99.5,
        threshold_critical=98.0,
        duration=300,
        group="health-monitor",
    ),
]


# ─── Alert Manager ────────────────────────────────────────────────────────────

class AlertManager:
    """Менеджер алертов: оценка правил, дедупликация, уведомления."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        cooldown: int = 300,
        state_file: str = "/tmp/playwright_alerts_state.json",
    ):
        self.rules = rules or ALERT_RULES
        self.cooldown = cooldown
        self.state_file = Path(state_file)
        self._active_alerts: dict[str, Alert] = {}
        self._last_fired: dict[str, float] = {}
        self._load_state()

    def _load_state(self):
        """Загрузить состояние алертов."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self._last_fired = data.get("last_fired", {})
            except Exception:
                pass

    def _save_state(self):
        """Сохранить состояние алертов."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({
                "last_fired": self._last_fired,
                "active_alerts": {
                    k: asdict(v) for k, v in self._active_alerts.items()
                },
            }, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save alert state: {e}")

    def evaluate(
        self,
        rule_name: str,
        current_value: float,
    ) -> Alert | None:
        """Оценить правило по текущему значению метрики.

        Args:
            rule_name: Имя правила из ALERT_RULES
            current_value: Текущее значение метрики

        Returns:
            Alert если сработал, None если нет
        """
        rule = None
        for r in self.rules:
            if r.name == rule_name:
                rule = r
                break

        if not rule:
            logger.warning(f"Unknown alert rule: {rule_name}")
            return None

        # Проверить cooldown
        now = time.time()
        last_fired = self._last_fired.get(rule_name, 0)
        if now - last_fired < self.cooldown:
            return None

        # Определить severity по порогам
        severity = None
        threshold = 0.0

        if current_value >= rule.threshold_critical:
            severity = Severity.CRITICAL
            threshold = rule.threshold_critical
        elif current_value >= rule.threshold_warning:
            severity = Severity.WARNING
            threshold = rule.threshold_warning

        if not severity:
            # Проверить разрешение активного алерта
            if rule_name in self._active_alerts:
                alert = self._active_alerts.pop(rule_name)
                alert.resolved = True
                alert.resolved_at = datetime.utcnow().isoformat()
                logger.info(f"✅ Alert resolved: {rule_name}")
                self._save_state()
            return None

        # Создать алерт
        alert = Alert(
            rule_name=rule_name,
            severity=severity,
            message=f"{rule.description} (value={current_value:.2f}, threshold={threshold:.2f})",
            timestamp=datetime.utcnow().isoformat(),
            value=current_value,
            threshold=threshold,
            group=rule.group,
        )

        self._active_alerts[rule_name] = alert
        self._last_fired[rule_name] = now
        self._save_state()

        emoji = "🔴" if severity == Severity.CRITICAL else "🟡"
        logger.warning(f"{emoji} ALERT [{severity}]: {alert.message}")

        return alert

    def get_active_alerts(self, group: str | None = None) -> list[Alert]:
        """Получить активные алерты."""
        alerts = list(self._active_alerts.values())
        if group:
            alerts = [a for a in alerts if a.group == group]
        return alerts

    def get_summary(self) -> dict:
        """Сводка по алертам."""
        critical = sum(1 for a in self._active_alerts.values() if a.severity == Severity.CRITICAL)
        warning = sum(1 for a in self._active_alerts.values() if a.severity == Severity.WARNING)
        return {
            "total_active": len(self._active_alerts),
            "critical": critical,
            "warning": warning,
            "groups": list(set(a.group for a in self._active_alerts.values())),
        }

    def to_prometheus_rules(self) -> str:
        """Экспортировать правила в формате Prometheus Alertmanager."""
        lines = ["groups:", "- name: playwright_alerts", "  rules:"]

        for rule in self.rules:
            severity = rule.severity.value
            lines.append(f"  - alert: {rule.name}")
            lines.append(f'    expr: {rule.condition}')
            if rule.duration:
                lines.append(f"    for: {rule.duration}s")
            lines.append('    labels:')
            lines.append(f'      severity: {severity}')
            lines.append(f'      group: {rule.group}')
            lines.append('    annotations:')
            lines.append(f'      summary: "{rule.description}"')
            lines.append(f'      description: "{rule.description}. Current value: ${{{rule.condition}}}"')
            lines.append("")

        return "\n".join(lines)


# ─── Фабрика ──────────────────────────────────────────────────────────────────

_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Получить singleton AlertManager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
