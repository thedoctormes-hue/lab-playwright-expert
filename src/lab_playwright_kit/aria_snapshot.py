"""
ARIA Snapshot модуль: работа с accessibility tree.

Использует Playwright ARIA snapshot для получения и сравнения
accessibility tree страницы. Полезно для:
  - Accessibility тестирования
  - Сравнения DOM-структур
  - Сериализации состояния страницы
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger
from playwright.async_api import Page


@dataclass
class SnapshotDiff:
    """Результат сравнения двух ARIA snapshot."""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    @property
    def summary(self) -> str:
        return (
            f"Added: {len(self.added)}, "
            f"Removed: {len(self.removed)}, "
            f"Changed: {len(self.changed)}"
        )


class ARIASnapshot:
    """Работа с accessibility tree через Playwright.

    Использует встроенный механизм ARIA snapshot Playwright
    для получения структурированного представления accessibility tree.

    Example:
        >>> snapshot = await ARIASnapshot.capture(page)
        >>> yaml_str = ARIASnapshot.to_yaml(snapshot)
        >>> restored = ARIASnapshot.from_yaml(yaml_str)
    """

    @staticmethod
    async def capture(page: Page, selector: str | None = None) -> str:
        """Получить ARIA snapshot страницы.

        Использует page.locator().aria_snapshot() — встроенный метод
        Playwright для получения accessibility tree в формате YAML.

        Args:
            page: Playwright Page объект
            selector: Опциональный CSS-селектор для ограничения области.
                     Если None — snapshot всей страницы.

        Returns:
            ARIA snapshot в формате YAML-строки.

        Example:
            >>> snapshot = await ARIASnapshot.capture(page)
            >>> snapshot = await ARIASnapshot.capture(page, "#main-content")
        """
        if selector:
            locator = page.locator(selector)
        else:
            locator = page.locator("body")

        snapshot = await locator.aria_snapshot()
        if snapshot is None:
            logger.warning("ARIA snapshot returned None — page may be empty")
            return ""

        logger.debug(f"ARIA snapshot captured: {len(snapshot)} chars")
        return snapshot

    @staticmethod
    def compare(snapshot_a: str, snapshot_b: str) -> SnapshotDiff:
        """Сравнить два ARIA snapshot.

        Сравнивает построчно, выявляя добавленные, удалённые
        и изменённые элементы accessibility tree.

        Args:
            snapshot_a: Первый snapshot (YAML-строка)
            snapshot_b: Второй snapshot (YAML-строка)

        Returns:
            SnapshotDiff с результатами сравнения.

        Example:
            >>> diff = ARIASnapshot.compare(before, after)
            >>> if diff.has_changes:
            ...     print(diff.summary)
        """
        if not snapshot_a and not snapshot_b:
            return SnapshotDiff()

        lines_a = _parse_snapshot_lines(snapshot_a)
        lines_b = _parse_snapshot_lines(snapshot_b)

        set_a = set(lines_a)
        set_b = set(lines_b)

        added = [line for line in lines_b if line not in set_a]
        removed = [line for line in lines_a if line not in set_b]

        # Изменённые: строки с одинаковым ключом, но разными значениями
        changed = _find_changed_lines(lines_a, lines_b)

        diff = SnapshotDiff(added=added, removed=removed, changed=changed)
        logger.info(f"ARIA snapshot diff: {diff.summary}")
        return diff

    @staticmethod
    def to_yaml(snapshot: str) -> str:
        """Сериализация ARIA snapshot в YAML.

        Поскольку Playwright aria_snapshot() уже возвращает YAML-формат,
        этот метод выполняет валидацию и нормализацию.

        Args:
            snapshot: ARIA snapshot строка

        Returns:
            Валидированная YAML-строка.

        Example:
            >>> yaml_str = ARIASnapshot.to_yaml(raw_snapshot)
        """
        if not snapshot:
            return ""

        # Нормализация: убираем лишние пустые строки, нормализуем отступы
        lines = snapshot.splitlines()
        normalized = []
        for line in lines:
            # Сохраняем строки с содержимым и структурные отступы
            stripped = line.rstrip()
            if stripped:
                normalized.append(stripped)

        result = "\n".join(normalized) + "\n"
        logger.debug(f"Serialized ARIA snapshot to YAML: {len(result)} chars")
        return result

    @staticmethod
    def from_yaml(yaml_str: str) -> str:
        """Десериализация ARIA snapshot из YAML.

        Валидирует и возвращает snapshot-строку, пригодную
        для сравнения или других операций.

        Args:
            yaml_str: YAML-строка ARIA snapshot

        Returns:
            Валидированная snapshot-строка.

        Raises:
            ValueError: Если YAML-строка имеет некорректный формат.

        Example:
            >>> snapshot = ARIASnapshot.from_yaml(yaml_str)
        """
        if not yaml_str or not yaml_str.strip():
            logger.warning("Empty YAML string provided to from_yaml")
            return ""

        # Базовая валидация: проверяем что строка содержит ARIA-элементы
        lines = yaml_str.strip().splitlines()
        valid_lines = [line for line in lines if line.strip()]

        if not valid_lines:
            raise ValueError("YAML string contains no valid ARIA snapshot lines")

        # Проверяем что строка похожа на ARIA snapshot
        # (содержит типы элементов или структуру с отступами)
        has_aria_structure = any(
            re.search(r"-\s+\w+", line) or  # ARIA role: - button, - heading, etc.
            re.search(r"\w+:", line) or       # key: value
            re.search(r"^\s+", line)          # indented (nested) element
            for line in valid_lines
        )

        if not has_aria_structure:
            raise ValueError(
                "YAML string does not appear to be a valid ARIA snapshot "
                "(no ARIA roles or structure detected)"
            )

        result = "\n".join(valid_lines) + "\n"
        logger.debug(f"Deserialized ARIA snapshot from YAML: {len(result)} chars")
        return result


def _parse_snapshot_lines(snapshot: str) -> list[str]:
    """Извлечь значимые строки из ARIA snapshot.

    Убирает пустые строки и нормализует отступы для сравнения.
    """
    if not snapshot:
        return []

    lines = snapshot.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            result.append(stripped)
    return result


def _find_changed_lines(
    lines_a: list[str],
    lines_b: list[str],
) -> list[dict[str, str]]:
    """Найти изменённые строки между двумя списками.

    Сравнивает строки с одинаковым ключом (до двоеточия),
    но разными значениями.
    """
    changed = []

    def _key(line: str) -> str:
        """Извлечь ключ строки (до первого ':')."""
        if ":" in line:
            # Убираем ARIA-префикс "- " если есть
            raw = line.split(":", 1)[0].strip()
            return raw.lstrip("- ").strip()
        return line

    def _value(line: str) -> str:
        """Извлечь значение строки (после первого ':')."""
        if ":" in line:
            return line.split(":", 1)[1].strip()
        return ""

    map_a = {_key(line): line for line in lines_a if ":" in line}
    map_b = {_key(line): line for line in lines_b if ":" in line}

    common_keys = set(map_a.keys()) & set(map_b.keys())
    for key in common_keys:
        val_a = _value(map_a[key])
        val_b = _value(map_b[key])
        if val_a != val_b:
            changed.append({"key": key, "before": val_a, "after": val_b})

    return changed
