"""
Расширенные тесты для ARIASnapshot и SnapshotDiff.

Покрывает:
  - SnapshotDiff: has_changes, summary
  - ARIASnapshot: to_yaml, from_yaml, compare (статические методы)
"""

from __future__ import annotations

from lab_playwright_kit.aria_snapshot import ARIASnapshot, SnapshotDiff


# ─── SnapshotDiff ────────────────────────────────────────────────────────


class TestSnapshotDiff:
    def test_default_empty(self):
        diff = SnapshotDiff()
        assert diff.added == []
        assert diff.removed == []
        assert diff.changed == []

    def test_has_changes_empty(self):
        diff = SnapshotDiff()
        assert diff.has_changes is False

    def test_has_changes_with_added(self):
        diff = SnapshotDiff(added=['button "OK"'])
        assert diff.has_changes is True

    def test_has_changes_with_removed(self):
        diff = SnapshotDiff(removed=['link "Home"'])
        assert diff.has_changes is True

    def test_has_changes_with_changed(self):
        diff = SnapshotDiff(changed=[{"key": "value"}])
        assert diff.has_changes is True

    def test_summary_empty(self):
        diff = SnapshotDiff()
        assert diff.summary == "Added: 0, Removed: 0, Changed: 0"

    def test_summary_with_data(self):
        diff = SnapshotDiff(
            added=["a", "b"],
            removed=["c"],
            changed=[{"k": "v"}, {"k2": "v2"}],
        )
        assert diff.summary == "Added: 2, Removed: 1, Changed: 2"


# ─── ARIASnapshot.to_yaml ────────────────────────────────────────────────


class TestToYaml:
    def test_empty_string(self):
        assert ARIASnapshot.to_yaml("") == ""

    def test_simple_yaml(self):
        raw = 'heading "Title"\nparagraph "Text"\n'
        result = ARIASnapshot.to_yaml(raw)
        assert "heading" in result
        assert "Title" in result

    def test_strips_trailing_whitespace(self):
        raw = 'heading "Title"   \nparagraph "Text"   \n'
        result = ARIASnapshot.to_yaml(raw)
        for line in result.splitlines():
            assert not line.endswith(" ")

    def test_removes_empty_lines(self):
        raw = 'heading "Title"\n\n\nparagraph "Text"\n'
        result = ARIASnapshot.to_yaml(raw)
        lines = result.splitlines()
        assert all(line.strip() for line in lines)

    def test_trailing_newline(self):
        raw = 'heading "Title"\n'
        result = ARIASnapshot.to_yaml(raw)
        assert result.endswith("\n")


# ─── ARIASnapshot.from_yaml ──────────────────────────────────────────────


class TestFromYaml:
    def test_empty_string(self):
        assert ARIASnapshot.from_yaml("") == ""

    def test_simple_yaml(self):
        yaml_str = '- heading "Title" [level=1]\n- paragraph "Text"\n'
        result = ARIASnapshot.from_yaml(yaml_str)
        assert "heading" in result


# ─── ARIASnapshot.compare ────────────────────────────────────────────────


class TestCompare:
    def test_both_empty(self):
        diff = ARIASnapshot.compare("", "")
        assert diff.has_changes is False

    def test_identical_snapshots(self):
        snap = 'heading "Title"\nparagraph "Text"\n'
        diff = ARIASnapshot.compare(snap, snap)
        assert diff.has_changes is False

    def test_added_lines(self):
        snap_a = 'heading "Title"\n'
        snap_b = 'heading "Title"\nparagraph "Text"\n'
        diff = ARIASnapshot.compare(snap_a, snap_b)
        assert len(diff.added) >= 1

    def test_removed_lines(self):
        snap_a = 'heading "Title"\nparagraph "Text"\n'
        snap_b = 'heading "Title"\n'
        diff = ARIASnapshot.compare(snap_a, snap_b)
        assert len(diff.removed) >= 1

    def test_summary_format(self):
        snap_a = 'heading "Title"\n'
        snap_b = 'heading "Title"\nparagraph "Text"\n'
        diff = ARIASnapshot.compare(snap_a, snap_b)
        assert "Added:" in diff.summary
        assert "Removed:" in diff.summary
        assert "Changed:" in diff.summary
