"""
Тесты для ARIA Snapshot модуля.

Покрывает:
  - ARIASnapshot.capture() — получение snapshot
  - ARIASnapshot.compare() — сравнение двух snapshot
  - ARIASnapshot.to_yaml() / from_yaml() — сериализация/десериализация
  - SnapshotDiff — результат сравнения
"""
import pytest

from lab_playwright_kit.aria_snapshot import ARIASnapshot, SnapshotDiff


# ─── SnapshotDiff ─────────────────────────────────────────────────────────────

class TestSnapshotDiff:
    def test_empty_diff_no_changes(self):
        diff = SnapshotDiff()
        assert not diff.has_changes
        assert diff.summary == "Added: 0, Removed: 0, Changed: 0"

    def test_diff_with_added(self):
        diff = SnapshotDiff(added=["- button \"OK\""])
        assert diff.has_changes
        assert "Added: 1" in diff.summary

    def test_diff_with_removed(self):
        diff = SnapshotDiff(removed=["- heading \"Title\""])
        assert diff.has_changes
        assert "Removed: 1" in diff.summary

    def test_diff_with_changed(self):
        diff = SnapshotDiff(changed=[{"key": "name", "before": "Alice", "after": "Bob"}])
        assert diff.has_changes
        assert "Changed: 1" in diff.summary

    def test_diff_combined(self):
        diff = SnapshotDiff(
            added=["- button \"Submit\""],
            removed=["- button \"Cancel\""],
            changed=[{"key": "value", "before": "old", "after": "new"}],
        )
        assert diff.has_changes
        assert "Added: 1" in diff.summary
        assert "Removed: 1" in diff.summary
        assert "Changed: 1" in diff.summary


# ─── ARIASnapshot.compare() ─────────────────────────────────────────────────

SIMPLE_SNAPSHOT_A = """- heading "Welcome"
- button "Login"
- text: Hello World
"""

SIMPLE_SNAPSHOT_B = """- heading "Welcome"
- button "Logout"
- text: Hello World
- link "About"
"""

EMPTY_SNAPSHOT = ""

IDENTICAL_SNAPSHOT = """- heading "Title"
- button "OK"
"""


class TestARIASnapshotCompare:
    def test_identical_snapshots_no_changes(self):
        diff = ARIASnapshot.compare(IDENTICAL_SNAPSHOT, IDENTICAL_SNAPSHOT)
        assert not diff.has_changes
        assert len(diff.added) == 0
        assert len(diff.removed) == 0

    def test_added_elements(self):
        diff = ARIASnapshot.compare(SIMPLE_SNAPSHOT_A, SIMPLE_SNAPSHOT_B)
        assert diff.has_changes
        assert any("About" in a for a in diff.added)

    def test_removed_elements(self):
        diff = ARIASnapshot.compare(SIMPLE_SNAPSHOT_B, SIMPLE_SNAPSHOT_A)
        assert diff.has_changes
        assert any("About" in r for r in diff.removed)

    def test_empty_vs_content(self):
        diff = ARIASnapshot.compare(EMPTY_SNAPSHOT, IDENTICAL_SNAPSHOT)
        assert diff.has_changes
        assert len(diff.added) > 0
        assert len(diff.removed) == 0

    def test_content_vs_empty(self):
        diff = ARIASnapshot.compare(IDENTICAL_SNAPSHOT, EMPTY_SNAPSHOT)
        assert diff.has_changes
        assert len(diff.removed) > 0
        assert len(diff.added) == 0

    def test_both_empty(self):
        diff = ARIASnapshot.compare(EMPTY_SNAPSHOT, EMPTY_SNAPSHOT)
        assert not diff.has_changes

    def test_changed_values(self):
        snap_a = "- button \"Login\"\n- text: old_value\n"
        snap_b = "- button \"Logout\"\n- text: new_value\n"
        diff = ARIASnapshot.compare(snap_a, snap_b)
        assert diff.has_changes


# ─── ARIASnapshot.to_yaml() ──────────────────────────────────────────────────

class TestARIASnapshotToYaml:
    def test_valid_snapshot(self):
        result = ARIASnapshot.to_yaml(SIMPLE_SNAPSHOT_A)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string(self):
        result = ARIASnapshot.to_yaml(EMPTY_SNAPSHOT)
        assert result == ""

    def test_normalizes_trailing_whitespace(self):
        snapshot = "- heading \"Title\"   \n  \n- button \"OK\"\n"
        result = ARIASnapshot.to_yaml(snapshot)
        # Должен убрать пустые строки и trailing whitespace
        for line in result.strip().splitlines():
            assert line == line.rstrip()

    def test_preserves_content(self):
        result = ARIASnapshot.to_yaml(SIMPLE_SNAPSHOT_A)
        assert "heading" in result
        assert "button" in result


# ─── ARIASnapshot.from_yaml() ────────────────────────────────────────────────

class TestARIASnapshotFromYaml:
    def test_valid_yaml(self):
        result = ARIASnapshot.from_yaml(SIMPLE_SNAPSHOT_A)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string_returns_empty(self):
        # from_yaml возвращает "" для пустой строки (с warning)
        result = ARIASnapshot.from_yaml("")
        assert result == ""

    def test_whitespace_only_returns_empty(self):
        # from_yaml возвращает "" для whitespace-only строки
        result = ARIASnapshot.from_yaml("   \n  \n  ")
        assert result == ""

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="does not appear to be a valid ARIA"):
            ARIASnapshot.from_yaml("just some random text without structure")

    def test_valid_aria_structure(self):
        valid = "- button \"Submit\"\n- heading \"Title\" level=1\n"
        result = ARIASnapshot.from_yaml(valid)
        assert "button" in result
        assert "heading" in result

    def test_key_value_structure(self):
        valid = "name: value\nrole: button\n"
        result = ARIASnapshot.from_yaml(valid)
        assert len(result) > 0


# ─── Интеграционные тесты ─────────────────────────────────────────────────────

class TestARIASnapshotIntegration:
    def test_roundtrip_to_yaml_from_yaml(self):
        original = "- heading \"Title\"\n- button \"OK\"\n- text: Hello\n"
        yaml_str = ARIASnapshot.to_yaml(original)
        restored = ARIASnapshot.from_yaml(yaml_str)
        assert "heading" in restored
        assert "button" in restored

    def test_compare_after_roundtrip(self):
        snap_a = "- heading \"Title\"\n- button \"OK\"\n"
        snap_b = "- heading \"Title\"\n- button \"Submit\"\n"

        yaml_a = ARIASnapshot.to_yaml(snap_a)
        yaml_b = ARIASnapshot.to_yaml(snap_b)

        restored_a = ARIASnapshot.from_yaml(yaml_a)
        restored_b = ARIASnapshot.from_yaml(yaml_b)

        diff = ARIASnapshot.compare(restored_a, restored_b)
        assert diff.has_changes

    def test_complex_snapshot(self):
        complex_snap = """
- heading "Main Page" level=1
- navigation "Main":
  - link "Home"
  - link "About"
  - link "Contact"
- form:
  - textbox "Search"
  - button "Go"
- contentinfo:
  - text: Copyright 2024
"""
        result = ARIASnapshot.to_yaml(complex_snap)
        assert "heading" in result
        assert "navigation" in result
        assert "form" in result

        restored = ARIASnapshot.from_yaml(result)
        assert len(restored) > 0
