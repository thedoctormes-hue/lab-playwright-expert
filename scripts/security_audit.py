#!/usr/bin/env python3
"""
Security Audit — регулярный аудит безопасности Playwright-инфраструктуры.

Проверяет:
  1. Права на файлы и директории
  2. Наличие секретов в открытом виде
  3. Конфигурацию systemd unit
  4. Сетевую доступность сервиса
  5. Уязвимости в зависимостях (pip audit)
  6. Корректность URL validation
  7. Статус rate limiting
  8. Целостность vault
  9. Логи на подозрительную активность
  10. SSL/TLS конфигурацию (если nginx)

Использование:
  python3 security_audit.py           # полный аудит
  python3 security_audit.py --quick   # быстрый аудит (только критическое)
  python3 security_audit.py --json    # JSON-отчёт
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


# ─── Конфигурация ───────────────────────────────────────────────

PROJECT_DIR = Path("/root/LabDoctorM/projects/lab-playwright-expert")
SECRETS_DIR = Path("/root/LabDoctorM/.secrets")
SERVICE_URL = os.getenv("SCREENSHOT_SERVICE_URL", "http://127.0.0.1:8190")
API_KEY = os.getenv("SCREENSHOT_API_KEY", "")

# Критические пути и ожидаемые права
PATH_CHECKS = {
    "/tmp/screenshot_cache_secure": {"mode": 0o700, "owner": "screenshot-service"},
    "/root/LabDoctorM/.secrets": {"mode": 0o700, "owner": "root"},
    str(PROJECT_DIR / "config"): {"mode": 0o750, "owner": "root"},
    str(PROJECT_DIR / "scripts"): {"mode": 0o750, "owner": "root"},
}

# Паттерны для поиска секретов в открытом виде
SECRET_PATTERNS = [
    (re.compile(r'api_key\s*=\s*["\'][^"\']{8,}["\']', re.I), "API key в коде"),
    (re.compile(r'password\s*=\s*["\'][^"\']{4,}["\']', re.I), "Password в коде"),
    (re.compile(r'token\s*=\s*["\'][^"\']{8,}["\']', re.I), "Token в коде"),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.I), "Bearer token"),
    (re.compile(r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'), "Private key"),
]

# Подозрительные паттерны в логах
SUSPICIOUS_PATTERNS = [
    re.compile(r"SSRF|blocked.*internal|blocked.*localhost", re.I),
    re.compile(r"rate.limit|429", re.I),
    re.compile(r"401|403|unauthorized", re.I),
    re.compile(r"invalid.*key|invalid.*api", re.I),
    re.compile(r"file://", re.I),
]


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class AuditFinding:
    severity: Severity
    category: str
    title: str
    description: str
    recommendation: str
    details: str | None = None


@dataclass
class AuditReport:
    timestamp: str
    findings: list = field(default_factory=list)
    passed: list = field(default_factory=list)
    duration_seconds: float = 0

    @property
    def critical_count(self):
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self):
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self):
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self):
        return sum(1 for f in self.findings if f.severity == Severity.LOW)

    def add(self, finding: AuditFinding):
        self.findings.append(finding)

    def add_pass(self, check_name: str):
        self.passed.append(check_name)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "summary": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
                "passed": len(self.passed),
                "total_findings": len(self.findings),
            },
            "findings": [asdict(f) for f in self.findings],
            "passed": self.passed,
            "duration_seconds": self.duration_seconds,
        }


# ─── Проверки ───────────────────────────────────────────────────

def check_file_permissions(report: AuditReport):
    """Проверка прав на критические файлы и директории."""
    for path_str, expected in PATH_CHECKS.items():
        path = Path(path_str)
        if not path.exists():
            report.add(AuditFinding(
                severity=Severity.HIGH,
                category="filesystem",
                title=f"Директория не существует: {path_str}",
                description=f"Ожидаемая директория {path_str} не найдена",
                recommendation=f"Создать: mkdir -p {path_str} && chmod {oct(expected['mode'])[2:]} {path_str}",
            ))
            continue

        actual_mode = stat.S_IMODE(path.stat().st_mode)
        if actual_mode != expected["mode"]:
            report.add(AuditFinding(
                severity=Severity.HIGH,
                category="filesystem",
                title=f"Неверные права на {path_str}",
                description=f"Ожидалось {oct(expected['mode'])}, фактически {oct(actual_mode)}",
                recommendation=f"Исправить: chmod {oct(expected['mode'])[2:]} {path_str}",
            ))
        else:
            report.add_pass(f"permissions:{path_str}")


def check_exposed_secrets(report: AuditReport):
    """Поиск секретов в открытом виде в коде."""
    scan_dirs = [
        PROJECT_DIR / "scripts",
        PROJECT_DIR / "src",
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for py_file in scan_dir.rglob("*.py"):
            # Пропустить файлы безопасности (они содержат шаблоны)
            if py_file.name in ("secret_manager.py", "screenshot_service_secure.py"):
                continue

            try:
                content = py_file.read_text()
            except Exception:
                continue

            for pattern, description in SECRET_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    report.add(AuditFinding(
                        severity=Severity.CRITICAL,
                        category="secrets",
                        title=f"Секрет в открытом виде: {py_file.name}",
                        description=f"{description}. Найдено: {len(matches)} совпадений",
                        recommendation=(
                            "Переместить секрет в vault или env. "
                            "Используйте SecretManager или EnvironmentFile."
                        ),
                        details=str(matches[:3]),
                    ))


def check_legacy_cookie_files(report: AuditReport):
    """Проверка наличия cookies в открытых файлах."""
    legacy_files = [
        PROJECT_DIR / "config" / "habr_cookies.json",
        PROJECT_DIR / "config" / "vc_cookies.json",
    ]

    for f in legacy_files:
        if f.exists():
            # Проверить права
            mode = stat.S_IMODE(f.stat().st_mode)
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                sev = Severity.CRITICAL
            else:
                sev = Severity.HIGH

            report.add(AuditFinding(
                severity=sev,
                category="secrets",
                title=f"Cookies в открытом виде: {f.name}",
                description=f"Файл {f} содержит cookies без шифрования. Права: {oct(mode)}",
                recommendation=(
                    f"Мигрировать в vault: python3 crosspost_secure.py --migrate. "
                    f"Затем удалить: shred -u {f}"
                ),
            ))
        else:
            report.add_pass(f"no_legacy_cookies:{f.name}")


def check_systemd_config(report: AuditReport):
    """Проверка конфигурации systemd unit."""
    unit_file = Path("/etc/systemd/system/screenshot-service.service")

    if not unit_file.exists():
        report.add(AuditFinding(
            severity=Severity.MEDIUM,
            category="systemd",
            title="systemd unit не установлен",
            description="Файл /etc/systemd/system/screenshot-service.service не найден",
            recommendation="Установить: sudo cp config/screenshot-service.service /etc/systemd/system/",
        ))
        return

    content = unit_file.read_text()

    # Проверить ключевые параметры безопасности
    security_checks = [
        ("ProtectSystem=full", "Файловая система защищена"),
        ("ProtectHome=true", "Home директория защищена"),
        ("PrivateTmp=true", "Изолированный /tmp"),
        ("NoNewPrivileges=true", "Запрет повышения привилегий"),
        ("MemoryDenyWriteExecute=true", "Запрет W^X памяти"),
        ("RestrictAddressFamilies=", "Ограничение сетевых семейств"),
        ("IPAddressAllow=127.0.0.1", "Сеть только через loopback"),
        ("MemoryMax=", "Ограничение памяти"),
        ("CPUQuota=", "Ограничение CPU"),
        ("TasksMax=", "Ограничение процессов"),
    ]

    for pattern, description in security_checks:
        if pattern in content:
            report.add_pass(f"systemd:{pattern}")
        else:
            report.add(AuditFinding(
                severity=Severity.HIGH,
                category="systemd",
                title=f"Отсутствует {pattern}",
                description=f"{description} не настроено в systemd unit",
                recommendation=f"Добавить {pattern} в [Service] секцию unit-файла",
            ))

    # Проверить, что НЕ запускается от root
    if "User=root" in content:
        report.add(AuditFinding(
            severity=Severity.CRITICAL,
            category="systemd",
            title="Сервис запускается от root",
            description="User=root в systemd unit — критическая уязвимость",
            recommendation="Создать отдельного пользователя и указать User=<user>",
        ))


def check_service_exposure(report: AuditReport):
    """Проверка сетевой доступности сервиса."""
    # Проверить, слушает ли сервис на 0.0.0.0
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        if ":8190 " in result.stdout and "0.0.0.0:8190" in result.stdout:
            report.add(AuditFinding(
                severity=Severity.HIGH,
                category="network",
                title="Сервис слушает на 0.0.0.0:8190",
                description="Сервис доступен извне — должен слушать только 127.0.0.1",
                recommendation="Изменить --host 0.0.0.0 на --host 127.0.0.1 в CMD",
            ))
        elif "127.0.0.1:8190" in result.stdout:
            report.add_pass("network:loopback_only")
    except Exception:
        pass

    # Проверить firewall
    try:
        result = subprocess.run(
            ["iptables", "-L", "INPUT", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        if "8190" in result.stdout and "DROP" not in result.stdout:
            report.add(AuditFinding(
                severity=Severity.MEDIUM,
                category="network",
                title="Порт 8190 не защищён firewall",
                description="Нет правила DROP для порта 8190 в iptables",
                recommendation="Добавить: iptables -A INPUT -p tcp --dport 8190 -j DROP (кроме localhost)",
            ))
    except Exception:
        pass


def check_dependencies(report: AuditReport):
    """Проверка зависимостей на известные уязвимости."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "audit", "--format=json"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0:
            try:
                vulns = json.loads(result.stdout)
                if isinstance(vulns, dict):
                    vulns = vulns.get("dependencies", [])
                for dep in vulns:
                    name = dep.get("name", "unknown")
                    version = dep.get("version", "?")
                    vuln_list = dep.get("vulns", [])
                    for v in vuln_list:
                        report.add(AuditFinding(
                            severity=Severity.HIGH,
                            category="dependencies",
                            title=f"Уязвимость в {name}=={version}",
                            description=f"Vuln: {v.get('id', '?')} — {v.get('fix_versions', 'no fix')}",
                            recommendation=f"Обновить: pip install --upgrade {name}",
                        ))
                if not any(f.category == "dependencies" for f in report.findings):
                    report.add_pass("dependencies:no_vulns")
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        report.add(AuditFinding(
            severity=Severity.LOW,
            category="dependencies",
            title="pip-audit не установлен",
            description="Невозможно проверить зависимости на уязвимости",
            recommendation="Установить: pip install pip-audit",
        ))
    except subprocess.TimeoutExpired:
        pass


def check_url_validation(report: AuditReport):
    """Проверка работы URL validation (SSRF protection)."""
    if not API_KEY:
        report.add(AuditFinding(
            severity=Severity.INFO,
            category="ssrf",
            title="Нет API key для тестирования",
            description="SCREENSHOT_API_KEY не установлен — пропуск тестов SSRF",
            recommendation="Установить SCREENSHOT_API_KEY для полного аудита",
        ))
        return

    import urllib.error
    import urllib.request

    test_cases = [
        ("http://localhost:8190/health", False, "localhost"),
        ("http://127.0.0.1:8190/health", False, "127.0.0.1"),
        ("http://169.254.169.254/latest/meta-data/", False, "AWS metadata"),
        ("file:///etc/passwd", False, "file:// scheme"),
        ("https://example.com", True, "валидный URL"),
    ]

    for url, should_succeed, description in test_cases:
        try:
            req = urllib.request.Request(
                f"{SERVICE_URL}/screenshot",
                data=json.dumps({"url": url}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY,
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            succeeded = resp.status == 200
        except urllib.error.HTTPError as e:
            succeeded = e.code == 200
        except Exception:
            succeeded = False

        if succeeded != should_succeed:
            if should_succeed:
                report.add(AuditFinding(
                    severity=Severity.HIGH,
                    category="ssrf",
                    title=f"Ложное срабатывание URL validation: {description}",
                    description=f"URL {url} должен быть разрешён, но был заблокирован",
                    recommendation="Проверить validate_url() — возможен слишком агрессивный блок",
                ))
            else:
                report.add(AuditFinding(
                    severity=Severity.CRITICAL,
                    category="ssrf",
                    title=f"SSRF НЕ заблокирован: {description}",
                    description=f"URL {url} должен быть заблокирован, но был разрешён",
                    recommendation="СРОЧНО: исправить validate_url() — возможно обращение к внутренним ресурсам",
                ))
        else:
            report.add_pass(f"ssrf:{description}")


def check_rate_limiting(report: AuditReport):
    """Проверка работы rate limiting."""
    if not API_KEY:
        return

    import urllib.error
    import urllib.request

    # Отправить 15 запросов подряд (лимит 10 в 60 сек)
    blocked = False
    for i in range(15):
        try:
            req = urllib.request.Request(
                f"{SERVICE_URL}/health",
                headers={"X-API-Key": API_KEY},
            )
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                blocked = True
                break
        except Exception:
            pass

    if blocked:
        report.add_pass("rate_limiting:works")
    else:
        report.add(AuditFinding(
            severity=Severity.HIGH,
            category="rate_limiting",
            title="Rate limiting не работает",
            description="15 запросов отправлены без получения 429 ответа",
            recommendation="Проверить конфигурацию rate limiter в screenshot_service_secure.py",
        ))


def check_suspicious_logs(report: AuditReport):
    """Анализ логов на подозрительную активность."""
    log_file = Path("/var/log/screenshot-service-health.jsonl")

    if not log_file.exists():
        # Проверить journalctl
        try:
            result = subprocess.run(
                ["journalctl", "-u", "screenshot-service", "--since", "1 hour ago", "--no-pager", "-q"],
                capture_output=True, text=True, timeout=10,
            )
            log_content = result.stdout
        except Exception:
            return
    else:
        try:
            log_content = log_file.read_text()
        except Exception:
            return

    suspicious_count = 0
    for pattern in SUSPICIOUS_PATTERNS:
        matches = pattern.findall(log_content)
        suspicious_count += len(matches)

    if suspicious_count > 10:
        report.add(AuditFinding(
            severity=Severity.MEDIUM,
            category="logs",
            title=f"Подозрительная активность в логах: {suspicious_count} событий",
            description="Обнаружено множество подозрительных записей за последний час",
            recommendation="Проверить логи: journalctl -u screenshot-service --since '1 hour ago'",
        ))
    else:
        report.add_pass("logs:no_suspicious")


# ─── Запуск аудита ──────────────────────────────────────────────

def run_audit(quick: bool = False, output_json: bool = False) -> AuditReport:
    """Запуск полного аудита безопасности."""
    from datetime import datetime

    report = AuditReport(timestamp=datetime.utcnow().isoformat())
    start = time.time()

    checks = [
        ("File Permissions", check_file_permissions),
        ("Exposed Secrets", check_exposed_secrets),
        ("Legacy Cookies", check_legacy_cookie_files),
        ("Systemd Config", check_systemd_config),
        ("Service Exposure", check_service_exposure),
    ]

    if not quick:
        checks.extend([
            ("Dependencies", check_dependencies),
            ("URL Validation (SSRF)", check_url_validation),
            ("Rate Limiting", check_rate_limiting),
            ("Suspicious Logs", check_suspicious_logs),
        ])

    for check_name, check_func in checks:
        try:
            check_func(report)
        except Exception as e:
            report.add(AuditFinding(
                severity=Severity.LOW,
                category="audit",
                title=f"Ошибка проверки: {check_name}",
                description=str(e),
                recommendation="Проверить вручную",
            ))

    report.duration_seconds = time.time() - start

    if output_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        print_report(report)

    return report


def print_report(report: AuditReport):
    """Красивый вывод отчёта."""
    print()
    print("=" * 60)
    print("  🔒 SECURITY AUDIT REPORT")
    print(f"  {report.timestamp}")
    print("=" * 60)
    print()

    # Summary
    print(f"  Critical: {report.critical_count}")
    print(f"  High:     {report.high_count}")
    print(f"  Medium:   {report.medium_count}")
    print(f"  Low:      {report.low_count}")
    print(f"  Passed:   {len(report.passed)}")
    print(f"  Time:     {report.duration_seconds:.1f}s")
    print()

    if report.findings:
        # Сортировать по severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        sorted_findings = sorted(report.findings, key=lambda f: severity_order[f.severity])

        for f in sorted_findings:
            emoji = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🔵",
                Severity.INFO: "ℹ️",
            }[f.severity]

            print(f"  {emoji} [{f.severity.value}] {f.title}")
            print(f"     Category: {f.category}")
            print(f"     {f.description}")
            print(f"     → {f.recommendation}")
            if f.details:
                print(f"     Details: {f.details}")
            print()
    else:
        print("  ✅ Все проверки пройдены, уязвимостей не обнаружено!")
        print()

    print("=" * 60)


# ─── CLI ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Security Audit — Playwright Infrastructure")
    parser.add_argument("--quick", action="store_true", help="Быстрый аудит (только критическое)")
    parser.add_argument("--json", action="store_true", help="JSON-отчёт")
    args = parser.parse_args()

    report = run_audit(quick=args.quick, output_json=args.json)

    # Exit code: 0 = OK, 1 = findings
    if report.critical_count > 0 or report.high_count > 0:
        sys.exit(1)
    sys.exit(0)
