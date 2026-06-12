"""
Stealth Score Tracker — отслеживание stealth score во времени.

Хранит историю замеров, вычисляет тренды, прогнозирует деградацию.
Формат: JSONL (по одной записи на замер).

Использование:
  python3 stealth_tracker.py --run          # запустить замер и сохранить
  python3 stealth_tracker.py --trend        # показать тренд
  python3 stealth_tracker.py --history 7d   # история за 7 дней
  python3 stealth_tracker.py --compare      # сравнить с предыдущим
  python3 stealth_tracker.py --forecast     # прогноз деградации
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger


# Пути
KIT_PATH = Path("/root/LabDoctorM/projects/lab-playwright-expert/src")
sys.path.insert(0, str(KIT_PATH))

HISTORY_FILE = Path("/var/log/stealth_score_history.jsonl")
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─── Модели ───────────────────────────────────────────────────────────────────

def create_record(
    overall_score: float,
    test_scores: dict[str, float],
    level: str = "full",
    metadata: dict | None = None,
) -> dict:
    """Создать запись замера."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "overall_score": overall_score,
        "test_scores": test_scores,
        "level": level,
        "metadata": metadata or {},
    }


def save_record(record: dict) -> None:
    """Сохранить запись в историю."""
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    logger.info(f"Stealth score saved: {record['overall_score']:.0f}%")


def load_history(days: int | None = None) -> list[dict]:
    """Загрузить историю замеров."""
    if not HISTORY_FILE.exists():
        return []

    records = []
    cutoff = None
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)

    with open(HISTORY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if cutoff:
                    record_time = datetime.fromisoformat(record["timestamp"])
                    if record_time < cutoff:
                        continue
                records.append(record)
            except Exception:
                continue

    return records


# ─── Анализ трендов ───────────────────────────────────────────────────────────

def compute_trend(records: list[dict]) -> dict:
    """Вычислить тренд по записям."""
    if len(records) < 2:
        return {"direction": "insufficient_data", "slope": 0, "r_squared": 0}

    scores = [r["overall_score"] for r in records]
    n = len(scores)

    # Линейная регрессия (x = индекс записи, y = score)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(scores)

    numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return {"direction": "stable", "slope": 0, "r_squared": 0}

    slope = numerator / denominator

    # R²
    ss_res = sum((s - (y_mean + slope * (i - x_mean))) ** 2 for i, s in enumerate(scores))
    ss_tot = sum((s - y_mean) ** 2 for s in scores)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Направление
    if slope > 0.5:
        direction = "improving"
    elif slope < -0.5:
        direction = "degrading"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "slope": slope,  # процентов на замер
        "r_squared": r_squared,
        "current": scores[-1],
        "min": min(scores),
        "max": max(scores),
        "mean": y_mean,
        "std": statistics.stdev(scores) if n > 1 else 0,
        "samples": n,
    }


def compute_test_trends(records: list[dict]) -> dict[str, dict]:
    """Тренды по каждому тесту."""
    if not records:
        return {}

    # Собрать все тесты
    all_tests = set()
    for r in records:
        all_tests.update(r.get("test_scores", {}).keys())

    trends = {}
    for test in all_tests:
        scores = []
        for r in records:
            if test in r.get("test_scores", {}):
                scores.append(r["test_scores"][test])

        if len(scores) >= 2:
            trends[test] = {
                "current": scores[-1],
                "min": min(scores),
                "max": max(scores),
                "mean": statistics.mean(scores),
                "degraded_count": sum(1 for s in scores if s < 100),
                "total": len(scores),
            }
        elif scores:
            trends[test] = {
                "current": scores[-1],
                "min": scores[-1],
                "max": scores[-1],
                "mean": scores[-1],
                "degraded_count": 0 if scores[-1] == 100 else 1,
                "total": 1,
            }

    return trends


def forecast_degradation(records: list[dict], threshold: float = 60.0) -> dict:
    """Прогноз: когда score упадёт ниже threshold."""
    if len(records) < 3:
        return {"forecast": "insufficient_data", "estimated_hours": None}

    scores = [r["overall_score"] for r in records]
    n = len(scores)

    # Линейная регрессия
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(scores)
    numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return {"forecast": "stable", "estimated_hours": None}

    slope = numerator / denominator

    if slope >= 0:
        return {"forecast": "not_degrading", "estimated_hours": None, "slope": slope}

    # Через сколько шагов достигнем threshold
    current = scores[-1]
    steps_to_threshold = (threshold - current) / slope

    if steps_to_threshold < 0:
        return {"forecast": "already_below", "estimated_hours": 0, "slope": slope}

    # Предполагаем замер каждые 6 часов
    hours_per_step = 6
    estimated_hours = steps_to_threshold * hours_per_step

    return {
        "forecast": "degrading",
        "estimated_hours": estimated_hours,
        "estimated_days": estimated_hours / 24,
        "slope": slope,
        "current": current,
        "threshold": threshold,
    }


# ─── Отчёты ───────────────────────────────────────────────────────────────────

def format_trend_report(records: list[dict]) -> str:
    """Форматировать отчёт по трендам."""
    if not records:
        return "📊 Stealth Score History: нет данных"

    trend = compute_trend(records)
    test_trends = compute_test_trends(records)
    forecast = forecast_degradation(records)

    lines = []
    lines.append("📊 **Stealth Score Trend Report**")
    lines.append(f"Период: {records[0]['date']} → {records[-1]['date']}")
    lines.append(f"Замеров: {trend['samples']}")
    lines.append("")

    # Общий тренд
    direction_emoji = {
        "improving": "📈",
        "degrading": "📉",
        "stable": "➡️",
        "insufficient_data": "❓",
    }
    emoji = direction_emoji.get(trend["direction"], "❓")
    lines.append(f"{emoji} **Тренд: {trend['direction']}**")
    lines.append(f"  Текущий: {trend['current']:.0f}%")
    lines.append(f"  Средний: {trend['mean']:.0f}%")
    lines.append(f"  Мин/Макс: {trend['min']:.0f}% / {trend['max']:.0f}%")
    lines.append(f"  Наклон: {trend['slope']:+.2f}%/замер")
    lines.append(f"  R²: {trend['r_squared']:.2f}")
    lines.append("")

    # По тестам
    if test_trends:
        lines.append("**По тестам:**")
        for test, data in test_trends.items():
            icon = "✅" if data["current"] == 100 else "❌"
            degraded = f" (деградаций: {data['degraded_count']}/{data['total']})" if data['degraded_count'] > 0 else ""
            lines.append(f"  {icon} {test}: {data['current']:.0f}% (avg: {data['mean']:.0f}%){degraded}")
        lines.append("")

    # Прогноз
    if forecast["forecast"] == "degrading":
        lines.append("⚠️ **Прогноз деградации:**")
        lines.append(f"  Упадёт ниже 60% через ~{forecast['estimated_days']:.1f} дней")
        lines.append(f"  Наклон: {forecast['slope']:.2f}%/замер")
    elif forecast["forecast"] == "already_below":
        lines.append("🔴 **Score уже ниже порога!**")
    elif forecast["forecast"] == "not_degrading":
        lines.append("✅ Деградация не обнаружена")

    return "\n".join(lines)


def format_history_report(records: list[dict], limit: int = 20) -> str:
    """Форматировать историю замеров."""
    if not records:
        return "📊 Stealth Score History: нет данных"

    lines = []
    lines.append("📊 **Stealth Score History**")
    lines.append(f"Показано последних {min(limit, len(records))} из {len(records)} замеров")
    lines.append("")

    for r in records[-limit:]:
        score = r["overall_score"]
        icon = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        date = r.get("date", "?")
        tests = r.get("test_scores", {})
        failed = [t for t, s in tests.items() if s < 100]
        failed_str = f" (❌ {', '.join(failed)})" if failed else ""
        lines.append(f"  {icon} {date}: {score:.0f}%{failed_str}")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run_measurement(level: str = "full") -> dict:
    """Запустить замер stealth score."""
    from stealth_research import StealthConfig, run_all_stealth_tests

    config_map = {
        "none": StealthConfig(enabled=False),
        "minimal": StealthConfig.minimal(),
        "full": StealthConfig.full(),
    }
    config = config_map.get(level, StealthConfig.full())

    report = await run_all_stealth_tests(config)

    test_scores = {}
    for r in report.results:
        test_scores[r.test_name] = 100.0 if r.passed else 0.0

    record = create_record(
        overall_score=report.score,
        test_scores=test_scores,
        level=level,
    )

    save_record(record)
    return record


async def main():
    parser = argparse.ArgumentParser(description="Stealth Score Tracker")
    parser.add_argument("--run", action="store_true", help="Запустить замер")
    parser.add_argument("--level", default="full", choices=["none", "minimal", "full"],
                        help="Уровень stealth для теста")
    parser.add_argument("--trend", action="store_true", help="Показать тренд")
    parser.add_argument("--history", type=str, default=None, help="История (7d, 30d, all)")
    parser.add_argument("--compare", action="store_true", help="Сравнить последние 2 замера")
    parser.add_argument("--forecast", action="store_true", help="Прогноз деградации")
    parser.add_argument("--json", action="store_true", help="Вывод в JSON")
    args = parser.parse_args()

    if args.run:
        record = await run_measurement(args.level)
        print(f"Stealth Score: {record['overall_score']:.0f}%")
        print(f"Tests: {record['test_scores']}")
        return

    # Парсим период
    days = None
    if args.history:
        if args.history.endswith("d"):
            days = int(args.history[:-1])
        elif args.history == "all":
            days = None
        else:
            days = int(args.history)

    records = load_history(days)

    if args.trend:
        report = format_trend_report(records)
        print(report)
        return

    if args.history:
        report = format_history_report(records)
        print(report)
        return

    if args.compare:
        if len(records) < 2:
            print("Недостаточно данных для сравнения")
            return
        prev = records[-2]
        curr = records[-1]
        diff = curr["overall_score"] - prev["overall_score"]
        emoji = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
        print(f"{emoji} Stealth Score: {prev['overall_score']:.0f}% → {curr['overall_score']:.0f}% ({diff:+.0f}%)")
        return

    if args.forecast:
        forecast = forecast_degradation(records)
        if args.json:
            print(json.dumps(forecast, indent=2))
        else:
            if forecast["forecast"] == "degrading":
                print(f"⚠️ Прогноз: score упадёт ниже 60% через ~{forecast['estimated_days']:.1f} дней")
            elif forecast["forecast"] == "already_below":
                print("🔴 Score уже ниже порога!")
            elif forecast["forecast"] == "not_degrading":
                print("✅ Деградация не обнаружена")
            else:
                print("❓ Недостаточно данных для прогноза")
        return

    # По умолчанию — тренд
    report = format_trend_report(records)
    print(report)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
