"""
E2E (end-to-end) tests for Lab Playwright Kit v2.0.

These tests verify full workflows across the six v2.0 modules:
  1. FingerprintManager  — generation, serialization, determinism
  2. HumanBehaviorEngine — profiles, Bezier curves, async API surface
  3. CaptchaSolver       — config, stats, mocked HTTP solve flows
  4. AccountManager      — full lifecycle, queries, cooldown, encryption
  5. ActionEngine        — behavior integration, ActionResult, counters
  6. TaskOrchestrator    — priority queue, handlers, rate limits, stats

Plus a cross-module integration workflow.

All tests are self-contained, independent, and use:
  - pytest-asyncio for async tests
  - unittest.mock for Playwright Page mocking
  - tempfile for SQLite DB isolation
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from lab_playwright_kit import (
    BEHAVIOR_PROFILES,
    AccountManager,
    AccountStatus,
    ActionEngine,
    ActionResult,
    ActionStep,
    ActionType,
    BehaviorProfile,
    BrowserFingerprint,
    CaptchaResult,
    CaptchaSolver,
    CaptchaType,
    FingerprintManager,
    HumanBehaviorEngine,
    RateLimit,
    SolverProvider,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FINGERPRINT E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestFingerprintE2E:
    """End-to-end fingerprint workflows: generate → serialize → reconstruct → verify."""

    def test_generate_to_dict_roundtrip_preserves_identity(self):
        """Full roundtrip: generate → to_dict → from_dict → verify all fields match."""
        fp = FingerprintManager.generate("e2e_roundtrip", os="windows", browser="chrome")
        d = fp.to_dict()
        restored = BrowserFingerprint.from_dict(d)

        assert restored.profile_id == fp.profile_id
        assert restored.user_agent == fp.user_agent
        assert restored.brand_version == fp.brand_version
        assert restored.webgl_vendor == fp.webgl_vendor
        assert restored.webgl_renderer == fp.webgl_renderer
        assert restored.webgl_version == fp.webgl_version
        assert restored.webgl_shading_language == fp.webgl_shading_language
        assert restored.webgl_extensions == fp.webgl_extensions
        assert restored.canvas_noise_seed == fp.canvas_noise_seed
        assert restored.audio_noise_seed == fp.audio_noise_seed
        assert restored.screen_width == fp.screen_width
        assert restored.screen_height == fp.screen_height
        assert restored.screen_avail_width == fp.screen_avail_width
        assert restored.screen_avail_height == fp.screen_avail_height
        assert restored.screen_color_depth == fp.screen_color_depth
        assert restored.screen_pixel_ratio == fp.screen_pixel_ratio
        assert restored.hardware_cores == fp.hardware_cores
        assert restored.hardware_memory == fp.hardware_memory
        assert restored.hardware_platform == fp.hardware_platform
        assert restored.fonts == fp.fonts
        assert restored.os == fp.os
        assert restored.timezone == fp.timezone
        assert restored.locale == fp.locale
        assert restored.languages == fp.languages

    def test_determinism_same_seed_produces_identical_fingerprints(self):
        """Generating twice with the same profile_name must yield identical results."""
        fp1 = FingerprintManager.generate("deterministic_user_42", os="linux", browser="firefox")
        fp2 = FingerprintManager.generate("deterministic_user_42", os="linux", browser="firefox")

        assert fp1.user_agent == fp2.user_agent
        assert fp1.webgl_renderer == fp2.webgl_renderer
        assert fp1.webgl_vendor == fp2.webgl_vendor
        assert fp1.canvas_noise_seed == fp2.canvas_noise_seed
        assert fp1.audio_noise_seed == fp2.audio_noise_seed
        assert fp1.screen_width == fp2.screen_width
        assert fp1.screen_height == fp2.screen_height
        assert fp1.hardware_cores == fp2.hardware_cores
        assert fp1.hardware_memory == fp2.hardware_memory
        assert fp1.hardware_platform == fp2.hardware_platform
        assert fp1.fonts == fp2.fonts
        assert fp1.timezone == fp2.timezone
        assert fp1.locale == fp2.locale
        assert fp1.languages == fp2.languages

    def test_different_seeds_produce_different_fingerprints(self):
        """Different profile names must produce different fingerprints."""
        fp1 = FingerprintManager.generate("user_alpha", os="windows", browser="chrome")
        fp2 = FingerprintManager.generate("user_beta", os="windows", browser="chrome")

        # At least one key field must differ
        assert (
            fp1.user_agent != fp2.user_agent
            or fp1.webgl_renderer != fp2.webgl_renderer
            or fp1.canvas_noise_seed != fp2.canvas_noise_seed
        )

    def test_multiple_os_browser_combos(self):
        """Generate fingerprints for all major OS/browser combinations."""
        combos = [
            ("windows", "chrome"),
            ("windows", "firefox"),
            ("windows", "edge"),
            ("macos", "chrome"),
            ("macos", "firefox"),
            ("macos", "safari"),
            ("linux", "chrome"),
            ("linux", "firefox"),
            ("android", "chrome"),
        ]

        fingerprints = {}
        for os_name, browser in combos:
            key = f"{browser}_{os_name}"
            fp = FingerprintManager.generate(f"combo_{key}", os=os_name, browser=browser)
            fingerprints[key] = fp

            # Verify OS consistency
            assert fp.os == os_name, f"OS mismatch for {key}"

            # Verify UA contains expected browser/os markers
            if os_name == "windows":
                assert "Windows" in fp.user_agent, f"UA should contain Windows for {key}"
            elif os_name == "macos":
                assert "Mac" in fp.user_agent or "macOS" in fp.user_agent, f"UA should mention Mac for {key}"
            elif os_name == "linux":
                assert "Linux" in fp.user_agent, f"UA should contain Linux for {key}"
            elif os_name == "android":
                assert "Android" in fp.user_agent, f"UA should contain Android for {key}"

            # Verify WebGL renderer is consistent with OS
            if os_name == "macos":
                assert "Mac" in fp.hardware_platform, f"Mac hardware platform expected for {key}"
            elif os_name == "linux":
                assert "Linux" in fp.hardware_platform, f"Linux hardware platform expected for {key}"
            elif os_name == "android":
                assert "Linux arm" in fp.hardware_platform, f"ARM platform expected for {key}"

        # All fingerprints should be unique (different seeds → different results)
        all_uas = [fp.user_agent for fp in fingerprints.values()]
        assert len(set(all_uas)) == len(all_uas), "All UA strings must be unique across combos"

    def test_explicit_seed_reproducibility(self):
        """Using an explicit seed integer must be reproducible."""
        fp1 = FingerprintManager.generate("seeded", os="windows", browser="chrome", seed=12345)
        fp2 = FingerprintManager.generate("seeded", os="windows", browser="chrome", seed=12345)

        assert fp1.to_dict() == fp2.to_dict()

    def test_summary_contains_key_info(self):
        """Summary string should contain profile_id, OS, screen, and GPU info."""
        fp = FingerprintManager.generate("summary_e2e", os="macos", browser="safari")
        s = fp.summary

        assert "summary_e2e" in s
        assert "macos" in s
        assert "Screen=" in s
        assert "Cores=" in s
        assert "RAM=" in s
        assert "GPU=" in s

    def test_canvas_and_audio_noise_hex_properties(self):
        """Hex noise properties should produce valid 8-char hex strings."""
        fp = FingerprintManager.generate("hex_test", os="windows", browser="chrome")

        assert len(fp.canvas_noise_hex) == 8
        assert len(fp.audio_noise_hex) == 8

        # Must be valid hex
        int(fp.canvas_noise_hex, 16)
        int(fp.audio_noise_hex, 16)

    def test_webgl_extensions_are_populated(self):
        """Generated fingerprint should have a realistic list of WebGL extensions."""
        fp = FingerprintManager.generate("ext_test", os="windows", browser="chrome")

        assert len(fp.webgl_extensions) > 20
        assert "WEBGL_debug_renderer_info" in fp.webgl_extensions
        assert "EXT_texture_filter_anisotropic" in fp.webgl_extensions

    def test_fonts_match_os(self):
        """Font list should correspond to the OS."""
        fp_win = FingerprintManager.generate("fonts_win", os="windows", browser="chrome")
        fp_mac = FingerprintManager.generate("fonts_mac", os="macos", browser="chrome")
        fp_lin = FingerprintManager.generate("fonts_lin", os="linux", browser="chrome")

        # Windows should have Segoe UI
        assert "Segoe UI" in fp_win.fonts
        # macOS should have SF Pro
        assert "SF Pro Text" in fp_mac.fonts
        # Linux should have DejaVu
        assert "DejaVu Sans" in fp_lin.fonts


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ACCOUNT MANAGER E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountManagerE2E:
    """End-to-end account lifecycle: create → warmup → active → cooldown → banned → delete."""

    def _make_db(self):
        """Create a temporary database and return (manager, path)."""
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return AccountManager(db_path=f.name), f.name

    def _cleanup(self, path):
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_full_account_lifecycle(self):
        """Create → WARMUP → ACTIVE → COOLDOWN → BANNED → DEAD, verifying at each step."""
        am, path = self._make_db()
        try:
            # 1. CREATE
            acc = am.create_account(
                platform="twitter",
                username="lifecycle_user",
                email="life@test.com",
                password="secret123",
            )
            assert acc.status == AccountStatus.CREATED
            assert acc.platform == "twitter"
            assert acc.username == "lifecycle_user"
            account_id = acc.id

            # 2. WARMUP
            am.update_status(account_id, AccountStatus.WARMUP)
            acc = am.get_account(account_id)
            assert acc.status == AccountStatus.WARMUP

            # 3. ACTIVE
            am.update_status(account_id, AccountStatus.ACTIVE)
            acc = am.get_account(account_id)
            assert acc.status == AccountStatus.ACTIVE

            # 4. COOLDOWN
            am.update_status(account_id, AccountStatus.COOLDOWN)
            acc = am.get_account(account_id)
            assert acc.status == AccountStatus.COOLDOWN
            assert acc.cooldown_until > time.time()

            # 5. BANNED
            am.update_status(account_id, AccountStatus.BANNED, reason="Rate limited")
            acc = am.get_account(account_id)
            assert acc.status == AccountStatus.BANNED

            # 6. DEAD
            am.update_status(account_id, AccountStatus.DEAD)
            acc = am.get_account(account_id)
            assert acc.status == AccountStatus.DEAD

        finally:
            self._cleanup(path)

    def test_create_multiple_accounts_and_query(self):
        """Create accounts on different platforms, query by platform and status."""
        am, path = self._make_db()
        try:
            am.create_account(platform="twitter", username="tw_1", email="tw1@test.com")
            am.create_account(platform="twitter", username="tw_2", email="tw2@test.com")
            am.create_account(platform="instagram", username="ig_1", email="ig1@test.com")
            am.create_account(platform="telegram", username="tg_1", email="tg1@test.com")

            # Query all
            all_accs = am.get_accounts()
            assert len(all_accs) == 4

            # Query by platform
            tw_accs = am.get_accounts(platform="twitter")
            assert len(tw_accs) == 2

            ig_accs = am.get_accounts(platform="instagram")
            assert len(ig_accs) == 1

            # Query by status
            created = am.get_accounts(status=AccountStatus.CREATED.value)
            assert len(created) == 4

            # Query by platform + status
            tw_created = am.get_accounts(platform="twitter", status=AccountStatus.CREATED.value)
            assert len(tw_created) == 2

        finally:
            self._cleanup(path)

    def test_duplicate_account_raises(self):
        """Creating the same platform/username twice must raise ValueError."""
        am, path = self._make_db()
        try:
            am.create_account(platform="twitter", username="dup_user")
            with pytest.raises(ValueError, match="already exists"):
                am.create_account(platform="twitter", username="dup_user")
        finally:
            self._cleanup(path)

    def test_action_recording_and_history(self):
        """Record multiple actions and verify history."""
        am, path = self._make_db()
        try:
            acc = am.create_account(platform="twitter", username="action_user")

            am.record_action(acc.id, "like", "https://twitter.com/post/1")
            am.record_action(acc.id, "retweet", "https://twitter.com/post/2")
            am.record_action(acc.id, "follow", "https://twitter.com/user_x")
            am.record_action(acc.id, "like", "https://twitter.com/post/3", status="failed", error="Rate limited")

            history = am.get_action_history(acc.id)
            assert len(history) == 4

            # Most recent first
            assert history[0]["action_type"] == "like"
            assert history[0]["status"] == "failed"

            assert history[1]["action_type"] == "follow"
            assert history[2]["action_type"] == "retweet"
            assert history[3]["action_type"] == "like"
            assert history[3]["status"] == "success"

            # Verify counters updated
            updated = am.get_account(acc.id)
            assert updated.total_actions == 4
            assert updated.daily_actions == 4

        finally:
            self._cleanup(path)

    def test_cooldown_mechanics(self):
        """Set cooldown and verify account is not available."""
        am, path = self._make_db()
        try:
            acc = am.create_account(platform="twitter", username="cooldown_user")
            am.update_status(acc.id, AccountStatus.ACTIVE)

            # Account should be available
            available = am.get_available_accounts("twitter")
            assert any(a.id == acc.id for a in available)

            # Set cooldown for 1 hour
            am.set_cooldown(acc.id, hours=1.0)
            updated = am.get_account(acc.id)
            assert updated.status == AccountStatus.COOLDOWN
            assert updated.cooldown_until > time.time()

            # Account should NOT be available now
            available = am.get_available_accounts("twitter")
            assert not any(a.id == acc.id for a in available)

        finally:
            self._cleanup(path)

    def test_password_encryption_roundtrip(self):
        """Password should be stored encrypted and retrievable via get_password."""
        am, path = self._make_db()
        try:
            am._encryption_key = "e2e-test-key-12345"
            original_password = "S3cur3_P@ssw0rd!"
            acc = am.create_account(
                platform="twitter",
                username="pwd_user",
                password=original_password,
            )

            # Password in DB should be encrypted (not plaintext)
            assert acc.password_encrypted != original_password
            assert len(acc.password_encrypted) > 0

            # Decryption should yield original
            decrypted = am.get_password(acc)
            assert decrypted == original_password

        finally:
            self._cleanup(path)

    def test_get_account_by_username(self):
        """Lookup account by platform + username."""
        am, path = self._make_db()
        try:
            am.create_account(platform="twitter", username="lookup_me", email="lookup@test.com")

            found = am.get_account_by_username("twitter", "lookup_me")
            assert found is not None
            assert found.username == "lookup_me"
            assert found.email == "lookup@test.com"

            not_found = am.get_account_by_username("twitter", "nonexistent")
            assert not_found is None

        finally:
            self._cleanup(path)

    def test_delete_account_removes_completely(self):
        """Deleted account should not be retrievable."""
        am, path = self._make_db()
        try:
            acc = am.create_account(platform="twitter", username="delete_me")
            account_id = acc.id

            assert am.get_account(account_id) is not None
            assert am.delete_account(account_id) is True
            assert am.get_account(account_id) is None
            assert am.delete_account(account_id) is False  # Already deleted

        finally:
            self._cleanup(path)

    def test_stats_aggregation(self):
        """Stats should correctly aggregate across accounts."""
        am, path = self._make_db()
        try:
            # Create accounts on different platforms
            tw = am.create_account(platform="twitter", username="stat_tw")
            ig = am.create_account(platform="instagram", username="stat_ig")
            am.create_account(platform="telegram", username="stat_tg")

            am.update_status(tw.id, AccountStatus.ACTIVE)
            am.update_status(ig.id, AccountStatus.ACTIVE)

            # Global stats
            stats = am.get_stats()
            assert stats["total"] == 3
            assert stats["by_status"]["created"] == 1  # telegram
            assert stats["by_status"]["active"] == 2  # twitter, instagram

            # Platform-specific stats
            tw_stats = am.get_stats(platform="twitter")
            assert tw_stats["total"] == 1
            assert tw_stats["platform"] == "twitter"

        finally:
            self._cleanup(path)

    def test_reset_daily_counters(self):
        """Reset daily counters should zero out daily_actions."""
        am, path = self._make_db()
        try:
            acc = am.create_account(platform="twitter", username="reset_user")
            am.record_action(acc.id, "like", "target1")
            am.record_action(acc.id, "like", "target2")

            updated = am.get_account(acc.id)
            assert updated.daily_actions == 2

            reset_count = am.reset_daily_counters()
            assert reset_count == 1

            updated = am.get_account(acc.id)
            assert updated.daily_actions == 0
            # total_actions should remain
            assert updated.total_actions == 2

        finally:
            self._cleanup(path)

    def test_account_with_metadata_and_tags(self):
        """Account with metadata and tags should be queryable."""
        am, path = self._make_db()
        try:
            acc = am.create_account(
                platform="twitter",
                username="meta_user",
                tags="bot,auto,test",
                metadata={"proxy": "socks5://1.2.3.4:1080", "region": "US"},
            )

            # Tags query
            tagged = am.get_accounts(tags="bot")
            assert len(tagged) == 1

            # Metadata accessible
            fetched = am.get_account(acc.id)
            assert fetched.metadata["proxy"] == "socks5://1.2.3.4:1080"
            assert fetched.metadata["region"] == "US"

        finally:
            self._cleanup(path)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ACTION ENGINE E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionEngineE2E:
    """End-to-end ActionEngine workflows: creation, behavior integration, results tracking."""

    def _make_mock_page(self):
        """Create a comprehensive mock Playwright Page."""
        page = MagicMock()
        page.goto = AsyncMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(return_value=0)
        page.mouse = MagicMock()
        page.mouse.move = AsyncMock()
        page.mouse.click = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.mouse.dblclick = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.locator = MagicMock(return_value=self._make_mock_locator())
        page.wait_for_selector = AsyncMock()
        return page

    def _make_mock_locator(self, count=1):
        """Create a mock Locator."""
        loc = MagicMock()
        loc.count = AsyncMock(return_value=count)
        loc.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 30})
        loc.click = AsyncMock()
        loc.dblclick = AsyncMock()
        loc.fill = AsyncMock()
        loc.type = AsyncMock()
        loc.press = AsyncMock()
        loc.scroll_into_view_if_needed = AsyncMock()
        loc.first = loc  # .first returns self for chaining
        return loc

    def test_engine_creation_with_default_profile(self):
        """ActionEngine should create with default social_media profile."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        assert engine.page is page
        assert engine.behavior is not None
        assert isinstance(engine.behavior, HumanBehaviorEngine)
        assert engine.behavior.profile.name == "social_media"

    def test_engine_creation_with_custom_profile(self):
        """ActionEngine should accept custom behavior profile."""
        page = self._make_mock_page()
        engine = ActionEngine(page, profile="researcher")

        assert engine.behavior.profile.name == "researcher"

    def test_engine_creation_with_seed(self):
        """ActionEngine should accept a seed for deterministic behavior."""
        page = self._make_mock_page()
        engine = ActionEngine(page, profile="casual_reader", seed=42)

        assert engine.behavior._rng is not None

    def test_action_result_creation_and_properties(self):
        """ActionResult should track success/failure correctly."""
        success_result = ActionResult(
            action_type=ActionType.LIKE,
            status="success",
            target="https://twitter.com/post/1",
            duration_ms=150.0,
        )
        assert success_result.is_success is True
        assert success_result.action_type == ActionType.LIKE

        fail_result = ActionResult(
            action_type=ActionType.COMMENT,
            status="failed",
            target="https://twitter.com/post/2",
            message="Element not found",
            duration_ms=5000.0,
        )
        assert fail_result.is_success is False
        assert fail_result.message == "Element not found"

    def test_engine_counters_start_at_zero(self):
        """Success and fail counters should start at zero."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        assert engine.success_count == 0
        assert engine.fail_count == 0
        assert len(engine.results) == 0

    def test_engine_results_accumulate(self):
        """Results should accumulate as actions are performed."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        # Manually add results to simulate action execution
        engine._results.append(ActionResult(action_type=ActionType.LIKE, status="success"))
        engine._results.append(ActionResult(action_type=ActionType.LIKE, status="success"))
        engine._results.append(ActionResult(action_type=ActionType.COMMENT, status="failed"))

        assert len(engine.results) == 3
        assert engine.success_count == 2
        assert engine.fail_count == 1

    def test_engine_results_returns_copy(self):
        """results property should return a copy, not the internal list."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        engine._results.append(ActionResult(action_type=ActionType.LIKE, status="success"))

        results = engine.results
        results.clear()  # Modifying the returned list

        assert len(engine.results) == 1  # Internal list unchanged

    @pytest.mark.asyncio
    async def test_navigate_success(self):
        """Navigate action should return success result."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        result = await engine.navigate("https://example.com")

        assert result.is_success is True
        assert result.action_type == ActionType.NAVIGATE
        assert result.target == "https://example.com"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_navigate_failure(self):
        """Navigate to invalid URL should return failed result."""
        page = self._make_mock_page()
        page.goto = AsyncMock(side_effect=Exception("net::ERR_CONNECTION_REFUSED"))
        engine = ActionEngine(page)

        result = await engine.navigate("https://invalid.example.com", timeout=1000)

        assert result.is_success is False
        assert result.action_type == ActionType.NAVIGATE
        assert "ERR_CONNECTION_REFUSED" in result.message

    @pytest.mark.asyncio
    async def test_wait_for_content_success(self):
        """wait_for_content should succeed when selector is found."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        result = await engine.wait_for_content("article.post")

        assert result.is_success is True
        assert result.action_type == ActionType.WAIT

    @pytest.mark.asyncio
    async def test_wait_for_content_failure(self):
        """wait_for_content should fail on timeout."""
        page = self._make_mock_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout 5000ms exceeded"))
        engine = ActionEngine(page)

        result = await engine.wait_for_content(".nonexistent", timeout=5000)

        assert result.is_success is False
        assert result.action_type == ActionType.WAIT

    @pytest.mark.asyncio
    async def test_like_skipped_when_no_button(self):
        """Like should return SKIPPED when no like button is found."""
        page = self._make_mock_page()
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        result = await engine.like()

        assert result.status == "skipped"
        assert result.action_type == ActionType.LIKE

    @pytest.mark.asyncio
    async def test_follow_skipped_when_no_button(self):
        """Follow should return SKIPPED when no follow button is found."""
        page = self._make_mock_page()
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        result = await engine.follow()

        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_repost_skipped_when_no_button(self):
        """Repost should return SKIPPED when no repost button is found."""
        page = self._make_mock_page()
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        result = await engine.repost()

        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_click_element_not_found(self):
        """click_element should return SKIPPED when element not found."""
        page = self._make_mock_page()
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        result = await engine.click_element(".nonexistent")

        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_type_in_field_not_found(self):
        """type_in_field should return SKIPPED when field not found."""
        page = self._make_mock_page()
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        result = await engine.type_in_field("#missing", "hello")

        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_execute_chain_continues_on_failure(self):
        """execute_chain with on_fail=continue should process all steps."""
        page = self._make_mock_page()
        # Make locators return count=0 so like/follow are skipped
        page.locator = MagicMock(return_value=self._make_mock_locator(count=0))
        engine = ActionEngine(page)

        steps = [
            ActionStep(action_type="navigate", params={"url": "https://example.com"}),
            ActionStep(action_type="like", params={}, on_fail="continue"),
            ActionStep(action_type="follow", params={}, on_fail="continue"),
        ]

        results = await engine.execute_chain(steps)

        assert len(results) == 3
        # First step (navigate) should succeed
        assert results[0].is_success is True
        # Like and follow should be skipped (no buttons)
        assert results[1].status == "skipped"
        assert results[2].status == "skipped"

    @pytest.mark.asyncio
    async def test_execute_chain_aborts_on_failure(self):
        """execute_chain with on_fail=abort should stop at first failure."""
        page = self._make_mock_page()
        page.goto = AsyncMock(side_effect=Exception("Connection refused"))
        engine = ActionEngine(page)

        steps = [
            ActionStep(action_type="navigate", params={"url": "https://bad.com"}, on_fail="abort"),
            ActionStep(action_type="like", params={}, on_fail="abort"),
        ]

        results = await engine.execute_chain(steps)

        # Should stop after first failure
        assert len(results) == 1
        assert results[0].is_success is False

    @pytest.mark.asyncio
    async def test_execute_chain_unknown_action(self):
        """execute_chain with unknown action type should return FAILED."""
        page = self._make_mock_page()
        engine = ActionEngine(page)

        steps = [
            ActionStep(action_type="unknown_action_xyz", params={}),
        ]

        results = await engine.execute_chain(steps)

        assert len(results) == 1
        assert results[0].is_success is False
        assert "Unknown action type" in results[0].message

    @pytest.mark.asyncio
    async def test_view_content_returns_success(self):
        """view_content should return a result (may be skipped if no content)."""
        page = self._make_mock_page()
        page.evaluate = AsyncMock(return_value=100)  # text length
        engine = ActionEngine(page)

        result = await engine.view_content(duration_seconds=0.1)

        assert result.action_type == ActionType.VIEW

    @pytest.mark.asyncio
    async def test_scroll_and_read_returns_result(self):
        """scroll_and_read should return a result."""
        page = self._make_mock_page()
        page.evaluate = AsyncMock(return_value=100)
        engine = ActionEngine(page)

        result = await engine.scroll_and_read(pages=0.1)

        assert result.action_type == ActionType.SCROLL


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TASK ORCHESTRATOR E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskOrchestratorE2E:
    """End-to-end TaskOrchestrator workflows: priority queue, handlers, rate limits."""

    def _make_task(self, **kwargs):
        defaults = dict(
            id="task_001",
            platform="telegram",
            action="like",
            target="https://t.me/test/123",
            params={},
        )
        defaults.update(kwargs)
        return Task(**defaults)

    def test_priority_queue_ordering(self):
        """Tasks should be dequeued in priority order (CRITICAL first, BACKGROUND last)."""
        # Use a fresh event loop to avoid conflicts with pytest-asyncio
        loop = asyncio.new_event_loop()

        try:
            orch = TaskOrchestrator(workers=1)

            # Add in random priority order
            orch.add_task(self._make_task(id="t_low", priority=TaskPriority.LOW))
            orch.add_task(self._make_task(id="t_critical", priority=TaskPriority.CRITICAL))
            orch.add_task(self._make_task(id="t_normal", priority=TaskPriority.NORMAL))
            orch.add_task(self._make_task(id="t_high", priority=TaskPriority.HIGH))
            orch.add_task(self._make_task(id="t_bg", priority=TaskPriority.BACKGROUND))

            # Register a handler that records execution order
            execution_order = []

            async def tracking_handler(task):
                execution_order.append(task.id)
                return {"ok": True}

            orch.register_handler("like", tracking_handler)

            # Run all tasks
            results = loop.run_until_complete(orch.run())

            # Verify all tasks executed
            assert len(results) == 5

            # Verify priority ordering: CRITICAL first, then HIGH, NORMAL, LOW, BACKGROUND
            assert execution_order[0] == "t_critical"
            assert execution_order[1] == "t_high"
            assert execution_order[2] == "t_normal"
            assert execution_order[3] == "t_low"
            assert execution_order[4] == "t_bg"
        finally:
            loop.close()

    def test_batch_task_addition(self):
        """add_tasks should add multiple tasks at once."""
        orch = TaskOrchestrator()

        tasks = [
            self._make_task(id=f"batch_{i}", target=f"https://t.me/test/{i}")
            for i in range(20)
        ]
        orch.add_tasks(tasks)

        assert orch.queue_size == 20

    def test_stats_reflect_queue_state(self):
        """Stats should accurately reflect current queue and processing state."""
        orch = TaskOrchestrator(workers=5)

        # Empty state
        stats = orch.stats
        assert stats["queue_size"] == 0
        assert stats["workers"] == 5
        assert stats["processed"] == 0
        assert stats["success"] == 0
        assert stats["failed"] == 0
        assert stats["running"] is False

        # After adding tasks
        orch.add_tasks([self._make_task(id=f"s_{i}") for i in range(7)])
        stats = orch.stats
        assert stats["queue_size"] == 7

    def test_register_single_handler(self):
        """register_handler should add a handler for a specific action."""
        orch = TaskOrchestrator()
        handler = AsyncMock(return_value={"result": "ok"})

        orch.register_handler("like", handler)

        assert "like" in orch._handlers
        assert orch._handlers["like"] is handler

    def test_register_multiple_handlers(self):
        """register_handlers should add multiple handlers at once."""
        orch = TaskOrchestrator()
        handlers = {
            "like": AsyncMock(),
            "comment": AsyncMock(),
            "follow": AsyncMock(),
            "repost": AsyncMock(),
        }

        orch.register_handlers(handlers)

        assert len(orch._handlers) == 4
        for action in handlers:
            assert action in orch._handlers

    def test_rate_limit_configuration(self):
        """set_rate_limit should configure rate limits for a platform."""
        orch = TaskOrchestrator()

        custom_rl = RateLimit(
            platform="custom_platform",
            max_per_minute=5,
            max_per_hour=50,
            max_per_day=200,
            cooldown_seconds=10.0,
        )

        orch.set_rate_limit("custom_platform", custom_rl)

        assert "custom_platform" in orch._rate_limits
        assert orch._rate_limits["custom_platform"].max_per_minute == 5
        assert orch._rate_limits["custom_platform"].cooldown_seconds == 10.0

    def test_rate_limit_can_execute_initially(self):
        """Fresh rate limit should allow execution."""
        rl = RateLimit(platform="test", max_per_minute=30, max_per_hour=500, max_per_day=5000)

        assert rl.can_execute() is True

    def test_rate_limit_blocks_after_cooldown(self):
        """Rate limit should block if cooldown hasn't elapsed."""
        rl = RateLimit(platform="test", max_per_minute=30, cooldown_seconds=5.0)
        rl.record_action()

        # Immediately after action, should be blocked by cooldown
        assert rl.can_execute() is False

    def test_rate_limit_respects_per_minute_cap(self):
        """Rate limit should block when per-minute cap is reached."""
        rl = RateLimit(platform="test", max_per_minute=3, max_per_hour=500, max_per_day=5000, cooldown_seconds=0)

        for _ in range(3):
            rl.record_action()

        assert rl.can_execute() is False

    def test_default_rate_limits_exist_for_major_platforms(self):
        """Default rate limits should be configured for all major platforms."""
        from lab_playwright_kit.task_orchestrator import DEFAULT_RATE_LIMITS

        major_platforms = [
            "twitter", "instagram", "facebook", "telegram", "vk",
            "reddit", "discord", "github", "habr", "vcru",
        ]

        for platform in major_platforms:
            assert platform in DEFAULT_RATE_LIMITS, f"Missing rate limit for {platform}"
            rl = DEFAULT_RATE_LIMITS[platform]
            assert rl.platform == platform
            assert rl.max_per_minute > 0
            assert rl.max_per_hour > 0
            assert rl.max_per_day > 0

    @pytest.mark.asyncio
    async def test_run_single_task(self):
        """run_single should execute a single task and return it with result."""
        orch = TaskOrchestrator()

        async def mock_handler(task):
            return {"status": "done", "target": task.target}

        orch.register_handler("like", mock_handler)

        task = self._make_task(id="single_test", action="like")
        result = await orch.run_single(task)

        assert result.status == TaskStatus.SUCCESS
        assert result.result["status"] == "done"
        assert result.completed_at > 0

    @pytest.mark.asyncio
    async def test_run_single_task_failure(self):
        """run_single should return FAILED status when handler raises."""
        orch = TaskOrchestrator()

        async def failing_handler(task):
            raise RuntimeError("Something went wrong")

        orch.register_handler("like", failing_handler)

        task = self._make_task(id="fail_test", action="like", max_retries=0)
        result = await orch.run_single(task)

        assert result.status == TaskStatus.FAILED
        assert "Something went wrong" in result.error

    @pytest.mark.asyncio
    async def test_run_single_task_no_handler(self):
        """run_single should return FAILED when no handler is registered."""
        orch = TaskOrchestrator()

        task = self._make_task(id="no_handler_test", action="unknown_action")
        result = await orch.run_single(task)

        assert result.status == TaskStatus.FAILED
        assert "No handler" in result.error

    @pytest.mark.asyncio
    async def test_run_empty_queue(self):
        """run with empty queue should return empty list."""
        orch = TaskOrchestrator()

        results = await orch.run()

        assert results == []

    @pytest.mark.asyncio
    async def test_task_timestamps_set_during_execution(self):
        """Task should have started_at and completed_at set after execution."""
        orch = TaskOrchestrator()

        async def slow_handler(task):
            await asyncio.sleep(0.01)
            return {"ok": True}

        orch.register_handler("like", slow_handler)

        task = self._make_task(id="timestamp_test")
        assert task.started_at == 0
        assert task.completed_at == 0

        result = await orch.run_single(task)

        assert result.started_at > 0
        assert result.completed_at > 0
        assert result.completed_at >= result.started_at

    @pytest.mark.asyncio
    async def test_retry_mechanism(self):
        """Task should retry on failure and eventually succeed."""
        orch = TaskOrchestrator()

        call_count = 0

        async def flaky_handler(task):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"Attempt {call_count} failed")
            return {"ok": True, "attempts": call_count}

        orch.register_handler("like", flaky_handler)

        task = self._make_task(id="retry_test", max_retries=3, retry_delay_seconds=0.01)
        result = await orch.run_single(task)

        assert result.status == TaskStatus.SUCCESS
        assert call_count == 3
        assert result.retry_count == 2  # Failed twice before succeeding

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Task should fail after max_retries is exhausted."""
        orch = TaskOrchestrator()

        async def always_fail(task):
            raise RuntimeError("Always fails")

        orch.register_handler("like", always_fail)

        task = self._make_task(id="exhaust_test", max_retries=2, retry_delay_seconds=0.01)
        result = await orch.run_single(task)

        assert result.status == TaskStatus.FAILED
        assert result.retry_count == 2  # 2 retries exhausted

    @pytest.mark.asyncio
    async def test_multiple_workers_process_tasks(self):
        """Multiple workers should process tasks concurrently."""
        orch = TaskOrchestrator(workers=3)

        processed = []

        async def handler(task):
            processed.append(task.id)
            return {"ok": True}

        orch.register_handler("like", handler)

        tasks = [self._make_task(id=f"worker_{i}") for i in range(9)]
        orch.add_tasks(tasks)

        results = await orch.run()

        assert len(results) == 9
        assert len(processed) == 9
        # All should succeed
        assert all(r.status == TaskStatus.SUCCESS for r in results)

    def test_task_priority_enum_values(self):
        """TaskPriority enum should have correct ordering."""
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.BACKGROUND

    def test_task_status_enum_values(self):
        """TaskStatus enum should have all expected values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.SUCCESS.value == "success"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.RETRY.value == "retry"
        assert TaskStatus.CANCELLED.value == "cancelled"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CAPTCHA SOLVER E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaptchaSolverE2E:
    """End-to-end CaptchaSolver workflows: config, stats, mocked solve flows."""

    def test_create_with_2captcha_provider(self):
        """CaptchaSolver should initialize with 2Captcha provider."""
        solver = CaptchaSolver(api_key="test_2captcha_key", provider="2captcha")

        assert solver.config.api_key == "test_2captcha_key"
        assert solver.config.provider == SolverProvider.TWOCAPTCHA
        assert solver.config.base_url_2captcha == "https://2captcha.com"

    def test_create_with_capsolver_provider(self):
        """CaptchaSolver should initialize with CapSolver provider."""
        solver = CaptchaSolver(api_key="test_capsolver_key", provider="capsolver")

        assert solver.config.provider == SolverProvider.CAPSOLVER
        assert solver.config.base_url_capsolver == "https://api.capsolver.com"

    def test_create_with_anticaptcha_provider(self):
        """CaptchaSolver should initialize with Anti-Captcha provider."""
        solver = CaptchaSolver(api_key="test_anti_key", provider="anticaptcha")

        assert solver.config.provider == SolverProvider.ANTICAPTCHA

    def test_default_timeout(self):
        """Default timeout should be 120 seconds."""
        solver = CaptchaSolver(api_key="test")
        assert solver.config.timeout_seconds == 120

    def test_custom_timeout(self):
        """Custom timeout should be respected."""
        solver = CaptchaSolver(api_key="test", timeout=60)
        assert solver.config.timeout_seconds == 60

    def test_initial_stats_are_zero(self):
        """Fresh solver should have zero stats."""
        solver = CaptchaSolver(api_key="test")
        stats = solver.stats

        assert stats["solved"] == 0
        assert stats["failed"] == 0
        assert stats["total"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_cost_usd"] == 0.0
        assert stats["provider"] == "2captcha"

    def test_stats_track_success(self):
        """Stats should track successful solves."""
        solver = CaptchaSolver(api_key="test")
        solver._solved_count = 5
        solver._failed_count = 1
        solver._total_cost = 0.01495

        stats = solver.stats
        assert stats["solved"] == 5
        assert stats["failed"] == 1
        assert stats["total"] == 6
        assert abs(stats["success_rate"] - (5 / 6 * 100)) < 0.01
        assert abs(stats["total_cost_usd"] - 0.01495) < 0.0001

    def test_stats_success_rate_with_no_solves(self):
        """Success rate should be 0 when no solves attempted."""
        solver = CaptchaSolver(api_key="test")
        stats = solver.stats
        assert stats["success_rate"] == 0.0

    def test_captcha_type_enum(self):
        """All captcha types should be defined."""
        assert CaptchaType.RECAPTCHA_V2.value == "recaptcha_v2"
        assert CaptchaType.RECAPTCHA_V3.value == "recaptcha_v3"
        assert CaptchaType.HCAPTCHA.value == "hcaptcha"
        assert CaptchaType.CLOUDFLARE_TURNSTILE.value == "cloudflare_turnstile"
        assert CaptchaType.YANDEX.value == "yandex"
        assert CaptchaType.FUNCAPTCHA.value == "funcaptcha"

    def test_captcha_result_dataclass(self):
        """CaptchaResult should hold all result fields."""
        result = CaptchaResult(
            success=True,
            token="03AGdBq24PBxt...",
            solve_time_ms=12500.0,
            cost=0.00299,
            captcha_id="7234567890",
        )

        assert result.success is True
        assert result.token == "03AGdBq24PBxt..."
        assert result.solve_time_ms == 12500.0
        assert result.cost == 0.00299
        assert result.captcha_id == "7234567890"
        assert result.error == ""

    def test_captcha_result_failure(self):
        """Failed CaptchaResult should have success=False and error message."""
        result = CaptchaResult(success=False, error="CAPCHA_NOT_READY")

        assert result.success is False
        assert result.token == ""
        assert result.error == "CAPCHA_NOT_READY"

    @pytest.mark.asyncio
    async def test_solve_recaptcha_v2_mocked(self):
        """solve_recaptcha_v2 should return CaptchaResult when HTTP is mocked."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"

        # Mock the HTTP client
        mock_in_response = MagicMock()
        mock_in_response.json.return_value = {"status": 1, "request": "task_12345"}

        mock_res_response = MagicMock()
        mock_res_response.json.return_value = {
            "status": 1,
            "request": "03AGdBq24PBxt...",
        }

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_in_response)
        solver._client.get = AsyncMock(return_value=mock_res_response)

        result = await solver.solve_recaptcha_v2(
            page, site_key="6Lc...test", url="https://example.com"
        )

        assert result.success is True
        assert result.token == "03AGdBq24PBxt..."
        assert result.captcha_id == "task_12345"

    @pytest.mark.asyncio
    async def test_solve_recaptcha_v2_no_site_key(self):
        """solve_recaptcha_v2 should fail gracefully when site_key cannot be detected."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(return_value=None)  # No site key found

        result = await solver.solve_recaptcha_v2(page)

        assert result.success is False
        assert "Could not detect" in result.error

    @pytest.mark.asyncio
    async def test_solve_hcaptcha_mocked(self):
        """solve_hcaptcha should return CaptchaResult when HTTP is mocked."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"

        mock_in_response = MagicMock()
        mock_in_response.json.return_value = {"status": 1, "request": "task_67890"}

        mock_res_response = MagicMock()
        mock_res_response.json.return_value = {
            "status": 1,
            "request": "hcap_token_abc123",
        }

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_in_response)
        solver._client.get = AsyncMock(return_value=mock_res_response)

        result = await solver.solve_hcaptcha(
            page, site_key="hcaptcha_site_key", url="https://example.com"
        )

        assert result.success is True
        assert result.token == "hcap_token_abc123"

    @pytest.mark.asyncio
    async def test_solve_cloudflare_turnstile_mocked(self):
        """solve_cloudflare_turnstile should return CaptchaResult when mocked."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"

        mock_in_response = MagicMock()
        mock_in_response.json.return_value = {"status": 1, "request": "task_turnstile_1"}

        mock_res_response = MagicMock()
        mock_res_response.json.return_value = {
            "status": 1,
            "request": "turnstile_token_xyz",
        }

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_in_response)
        solver._client.get = AsyncMock(return_value=mock_res_response)

        result = await solver.solve_cloudflare_turnstile(
            page, site_key="turnstile_key", url="https://example.com"
        )

        assert result.success is True
        assert result.token == "turnstile_token_xyz"

    @pytest.mark.asyncio
    async def test_auto_solve_no_captcha_detected(self):
        """auto_solve should return failure when no captcha is on the page."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(return_value=False)  # No captcha found

        result = await solver.auto_solve(page)

        assert result.success is False
        assert "No captcha detected" in result.error

    @pytest.mark.asyncio
    async def test_auto_solve_detects_recaptcha_v2(self):
        """auto_solve should detect and solve reCAPTCHA v2."""
        solver = CaptchaSolver(api_key="test_key", provider="2captcha")
        page = MagicMock()
        page.url = "https://example.com"

        # First evaluate call: _has_recaptcha_v2 returns True
        # Second evaluate call: _detect_recaptcha_site_key returns a site key
        page.evaluate = AsyncMock(side_effect=[True, "6Lc_aTsUAAAAAL6yVvj2YJ9gYx9yZzZzZzZz"])

        # Mock HTTP
        mock_in_response = MagicMock()
        mock_in_response.json.return_value = {"status": 1, "request": "auto_task_1"}

        mock_res_response = MagicMock()
        mock_res_response.json.return_value = {
            "status": 1,
            "request": "auto_token_123",
        }

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_in_response)
        solver._client.get = AsyncMock(return_value=mock_res_response)

        result = await solver.auto_solve(page)

        assert result.success is True
        assert result.token == "auto_token_123"

    @pytest.mark.asyncio
    async def test_close_http_client(self):
        """close() should close the HTTP client."""
        solver = CaptchaSolver(api_key="test")
        solver._client = AsyncMock()
        solver._client.aclose = AsyncMock()

        await solver.close()

        solver._client.aclose.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. HUMAN BEHAVIOR E2E
# ═══════════════════════════════════════════════════════════════════════════════

class TestHumanBehaviorE2E:
    """End-to-end HumanBehaviorEngine workflows: profiles, Bezier, async API."""

    def _make_mock_page(self):
        page = MagicMock()
        page.mouse = MagicMock()
        page.mouse.move = AsyncMock()
        page.mouse.click = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.mouse.dblclick = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.evaluate = AsyncMock(return_value=0)
        return page

    def test_all_four_profile_presets_exist(self):
        """All four behavior profile presets should be defined."""
        assert "casual_reader" in BEHAVIOR_PROFILES
        assert "power_user" in BEHAVIOR_PROFILES
        assert "researcher" in BEHAVIOR_PROFILES
        assert "social_media" in BEHAVIOR_PROFILES

    def test_profile_presets_have_distinct_parameters(self):
        """Different profiles should have distinct parameter ranges."""
        casual = BEHAVIOR_PROFILES["casual_reader"]
        power = BEHAVIOR_PROFILES["power_user"]

        # Power user should be faster
        assert power.mouse_move_max_ms < casual.mouse_move_max_ms
        assert power.scroll_speed_px[0] > casual.scroll_speed_px[0]
        assert power.typing_speed_wpm[0] > casual.typing_speed_wpm[0]

    def test_engine_with_string_profile(self):
        """Engine should accept string profile name."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, profile="researcher")

        assert engine.profile.name == "researcher"

    def test_engine_with_dataclass_profile(self):
        """Engine should accept BehaviorProfile dataclass."""
        page = self._make_mock_page()
        custom = BehaviorProfile(name="custom", mouse_move_min_ms=50, mouse_move_max_ms=200)
        engine = HumanBehaviorEngine(page, profile=custom)

        assert engine.profile.name == "custom"
        assert engine.profile.mouse_move_min_ms == 50

    def test_engine_with_invalid_profile_string_falls_back(self):
        """Engine with unknown profile string should fall back to casual_reader."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, profile="nonexistent_profile")

        assert engine.profile.name == "casual_reader"

    def test_engine_with_seed_deterministic(self):
        """Engine with same seed should produce same Bezier points."""
        page = self._make_mock_page()
        engine1 = HumanBehaviorEngine(page, seed=42)
        engine2 = HumanBehaviorEngine(page, seed=42)

        points1 = engine1._generate_bezier_points(0, 0, 100, 100, 20)
        points2 = engine2._generate_bezier_points(0, 0, 100, 100, 20)

        assert points1 == points2

    def test_engine_with_different_seeds_produces_different_points(self):
        """Engine with different seeds should produce different Bezier points."""
        page = self._make_mock_page()
        engine1 = HumanBehaviorEngine(page, seed=1)
        engine2 = HumanBehaviorEngine(page, seed=999)

        points1 = engine1._generate_bezier_points(0, 0, 100, 100, 20)
        points2 = engine2._generate_bezier_points(0, 0, 100, 100, 20)

        assert points1 != points2

    def test_bezier_points_start_and_end(self):
        """Bezier curve should start near origin and end near target."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, seed=42)

        points = engine._generate_bezier_points(10, 20, 500, 300, 50)

        # First point should be close to start
        assert abs(points[0][0] - 10) < 1.0
        assert abs(points[0][1] - 20) < 1.0

        # Last point should be close to end
        assert abs(points[-1][0] - 500) < 1.0
        assert abs(points[-1][1] - 300) < 1.0

    def test_bezier_points_count(self):
        """Bezier generation should return num_points + 1 points."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        for n in [5, 10, 20, 50]:
            points = engine._generate_bezier_points(0, 0, 100, 100, n)
            assert len(points) == n + 1

    def test_bezier_points_are_monotonic_approximate(self):
        """Bezier points should generally move from start to end (not teleport)."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, seed=42)

        points = engine._generate_bezier_points(0, 0, 300, 300, 30)

        # Consecutive points should not jump too far
        for i in range(1, len(points)):
            dx = abs(points[i][0] - points[i - 1][0])
            dy = abs(points[i][1] - points[i - 1][1])
            assert dx < 100, f"Large X jump at index {i}: {dx}"
            assert dy < 100, f"Large Y jump at index {i}: {dy}"

    def test_all_public_methods_exist(self):
        """All documented public methods should exist."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        public_methods = [
            'move_mouse_to', 'move_mouse_to_element', 'click', 'double_click',
            'hover', 'scroll_down', 'scroll_up', 'scroll_to_top',
            'scroll_to_bottom', 'scroll_to_element', 'type_text',
            'type_like_human', 'read_page', 'read_article',
            'wait_between_actions', 'random_idle',
        ]

        for method_name in public_methods:
            assert hasattr(engine, method_name), f"Missing method: {method_name}"
            assert callable(getattr(engine, method_name)), f"Not callable: {method_name}"

    def test_async_methods_are_coroutines(self):
        """All action methods should be async (coroutine functions)."""
        import inspect

        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        async_methods = [
            'move_mouse_to', 'move_mouse_to_element', 'click', 'double_click',
            'hover', 'scroll_down', 'scroll_up', 'scroll_to_top',
            'scroll_to_bottom', 'scroll_to_element', 'type_text',
            'type_like_human', 'read_page', 'read_article',
            'wait_between_actions', 'random_idle',
        ]

        for method_name in async_methods:
            method = getattr(engine, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"

    def test_internal_methods(self):
        """Internal methods like _generate_bezier_points should exist."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        assert hasattr(engine, '_generate_bezier_points')
        assert callable(engine._generate_bezier_points)

    def test_profile_parameters_accessible(self):
        """Profile parameters should be accessible and within realistic ranges."""
        page = self._make_mock_page()

        for profile_name in ["casual_reader", "power_user", "researcher", "social_media"]:
            engine = HumanBehaviorEngine(page, profile=profile_name)
            p = engine.profile

            # Mouse move should be positive
            assert p.mouse_move_min_ms > 0
            assert p.mouse_move_max_ms > p.mouse_move_min_ms

            # Scroll speed should be positive
            assert p.scroll_speed_px[0] > 0
            assert p.scroll_speed_px[1] > p.scroll_speed_px[0]

            # Typing speed should be positive
            assert p.typing_speed_wpm[0] > 0
            assert p.typing_speed_wpm[1] > p.typing_speed_wpm[0]

            # Error rate should be 0-1
            assert 0 <= p.typing_error_chance <= 1

    def test_current_position_tracking(self):
        """Engine should track current mouse position."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        # Default position
        assert engine._current_x == 0
        assert engine._current_y == 0

    @pytest.mark.asyncio
    async def test_move_mouse_to_updates_position(self):
        """move_mouse_to should update internal position tracking."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, seed=42)

        await engine.move_mouse_to(500, 300)

        assert engine._current_x == 500
        assert engine._current_y == 300

    @pytest.mark.asyncio
    async def test_move_mouse_to_calls_page_mouse_move(self):
        """move_mouse_to should call page.mouse.move for each Bezier point."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page, seed=42)

        await engine.move_mouse_to(100, 100)

        # Should have called mouse.move multiple times (at least 5 for short distance)
        assert page.mouse.move.call_count >= 5

    @pytest.mark.asyncio
    async def test_click_at_current_position(self):
        """Click without coordinates should click at current position."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.click()

        # Should have called mouse.click
        page.mouse.click.assert_called()

    @pytest.mark.asyncio
    async def test_double_click_with_coordinates(self):
        """Double click with coordinates should call page.mouse.dblclick."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.double_click(x=200, y=150)

        page.mouse.dblclick.assert_called_with(200, 150)

    @pytest.mark.asyncio
    async def test_scroll_down_calls_wheel(self):
        """scroll_down should call page.mouse.wheel."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.scroll_down(pages=0.1)

        # Should have called wheel at least once
        assert page.mouse.wheel.call_count >= 1

    @pytest.mark.asyncio
    async def test_scroll_up_calls_wheel_negative(self):
        """scroll_up should call wheel with negative delta."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.scroll_up(pages=0.1)

        # Check that wheel was called with negative y
        call_args = page.mouse.wheel.call_args
        assert call_args[0][1] < 0  # deltaY should be negative

    @pytest.mark.asyncio
    async def test_type_text_calls_keyboard(self):
        """type_text should call page.keyboard.press for each character."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.type_text("abc")

        # Should have called press for each character (plus possible error corrections)
        assert page.keyboard.press.call_count >= 3

    @pytest.mark.asyncio
    async def test_type_like_human_calls_keyboard(self):
        """type_like_human should call page.keyboard.type."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.type_like_human("hello world")

        # Should have called type at least once
        assert page.keyboard.type.call_count >= 1

    @pytest.mark.asyncio
    async def test_wait_between_actions_completes(self):
        """wait_between_actions should complete without error."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        # Should complete (uses asyncio.sleep internally)
        await engine.wait_between_actions()

    @pytest.mark.asyncio
    async def test_random_idle_completes(self):
        """random_idle should complete without error."""
        page = self._make_mock_page()
        engine = HumanBehaviorEngine(page)

        await engine.random_idle()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. INTEGRATION E2E — Cross-Module Workflow
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationE2E:
    """Cross-module integration: Fingerprint → Account → ActionEngine → TaskOrchestrator."""

    def _make_mock_page(self):
        page = MagicMock()
        page.goto = AsyncMock()
        page.url = "https://example.com"
        page.evaluate = AsyncMock(return_value=0)
        page.mouse = MagicMock()
        page.mouse.move = AsyncMock()
        page.mouse.click = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.mouse.dblclick = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.locator = MagicMock(return_value=self._make_mock_locator())
        page.wait_for_selector = AsyncMock()
        return page

    def _make_mock_locator(self, count=0):
        loc = MagicMock()
        loc.count = AsyncMock(return_value=count)
        loc.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 30})
        loc.click = AsyncMock()
        loc.dblclick = AsyncMock()
        loc.fill = AsyncMock()
        loc.type = AsyncMock()
        loc.press = AsyncMock()
        loc.scroll_into_view_if_needed = AsyncMock()
        loc.first = loc
        return loc

    def _make_db(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return AccountManager(db_path=f.name), f.name

    def _cleanup(self, path):
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_fingerprint_to_account_profile_binding(self):
        """Create fingerprint and bind it to an account via profile_id."""
        am, path = self._make_db()
        try:
            # Generate a fingerprint
            fp = FingerprintManager.generate("integration_user_1", os="windows", browser="chrome")

            # Create account with fingerprint binding
            acc = am.create_account(
                platform="twitter",
                username="integration_user_1",
                email="int@test.com",
                password="int_pass_123",
                profile_id=fp.profile_id,
            )

            assert acc.profile_id == fp.profile_id
            assert acc.profile_id == "integration_user_1"

            # Retrieve and verify binding persists
            fetched = am.get_account(acc.id)
            assert fetched.profile_id == fp.profile_id

        finally:
            self._cleanup(path)

    def test_fingerprint_determinism_across_sessions(self):
        """Same fingerprint profile should be reproducible across 'sessions'."""
        # Simulate session 1
        fp1 = FingerprintManager.generate("cross_session_user", os="macos", browser="chrome")

        # Simulate session 2 (same user, same profile)
        fp2 = FingerprintManager.generate("cross_session_user", os="macos", browser="chrome")

        assert fp1.to_dict() == fp2.to_dict()

    @pytest.mark.asyncio
    async def test_account_action_workflow(self):
        """Full workflow: create account → record actions → verify stats."""
        am, path = self._make_db()
        try:
            acc = am.create_account(
                platform="twitter",
                username="workflow_user",
                email="wf@test.com",
                password="wf_pass",
            )
            am.update_status(acc.id, AccountStatus.ACTIVE)

            # Record a series of actions
            actions = [
                ("like", "https://twitter.com/post/1"),
                ("like", "https://twitter.com/post/2"),
                ("retweet", "https://twitter.com/post/3"),
                ("follow", "https://twitter.com/target_user"),
                ("comment", "https://twitter.com/post/4"),
            ]

            for action_type, target in actions:
                am.record_action(acc.id, action_type, target)

            # Verify
            updated = am.get_account(acc.id)
            assert updated.total_actions == 5
            assert updated.daily_actions == 5

            history = am.get_action_history(acc.id)
            assert len(history) == 5

            stats = am.get_stats(platform="twitter")
            assert stats["total"] == 1
            assert stats["total_actions"] == 5

        finally:
            self._cleanup(path)

    @pytest.mark.asyncio
    async def test_action_engine_with_mocked_page_full_flow(self):
        """ActionEngine: navigate → scroll → verify results tracking."""
        page = self._make_mock_page()
        engine = ActionEngine(page, profile="social_media", seed=42)

        # Navigate
        nav_result = await engine.navigate("https://twitter.com")
        assert nav_result.is_success is True

        # Scroll and read
        scroll_result = await engine.scroll_and_read(pages=0.1)
        assert scroll_result.action_type == ActionType.SCROLL

        # Verify results accumulated
        assert len(engine.results) >= 2
        assert engine.success_count >= 1  # At least navigate succeeded

    @pytest.mark.asyncio
    async def test_orchestrator_with_multiple_platforms(self):
        """Orchestrator should handle tasks for different platforms with separate rate limits."""
        orch = TaskOrchestrator(workers=2)

        processed = []

        async def handler(task):
            processed.append((task.platform, task.id))
            return {"ok": True}

        orch.register_handler("like", handler)

        # Add tasks for different platforms
        orch.add_task(Task(platform="twitter", action="like", target="t/1", id="tw_1"))
        orch.add_task(Task(platform="instagram", action="like", target="ig/1", id="ig_1"))
        orch.add_task(Task(platform="telegram", action="like", target="tg/1", id="tg_1"))
        orch.add_task(Task(platform="twitter", action="like", target="t/2", id="tw_2"))

        results = await orch.run()

        assert len(results) == 4
        assert len(processed) == 4

        # Verify all platforms were processed
        platforms_processed = {p for p, _ in processed}
        assert "twitter" in platforms_processed
        assert "instagram" in platforms_processed
        assert "telegram" in platforms_processed

    @pytest.mark.asyncio
    async def test_full_integration_fingerprint_account_action_orchestrator(self):
        """
        Complete cross-module workflow:
        1. Generate fingerprint
        2. Create account bound to fingerprint
        3. Create ActionEngine with behavior profile
        4. Create tasks in orchestrator
        5. Execute and verify end-to-end
        """
        # Step 1: Generate fingerprint
        fp = FingerprintManager.generate("full_integration_user", os="windows", browser="chrome")
        assert fp.profile_id == "full_integration_user"

        # Step 2: Create account with fingerprint binding
        am, path = self._make_db()
        try:
            acc = am.create_account(
                platform="twitter",
                username="full_integration_user",
                email="full@test.com",
                password="full_pass",
                profile_id=fp.profile_id,
                tags="integration,test",
            )
            am.update_status(acc.id, AccountStatus.ACTIVE)

            # Verify account is available
            available = am.get_available_accounts("twitter")
            assert any(a.id == acc.id for a in available)

            # Step 3: Create ActionEngine with behavior profile
            page = self._make_mock_page()
            engine = ActionEngine(page, profile="social_media", seed=42)

            # Verify behavior integration
            assert engine.behavior is not None
            assert engine.behavior.profile.name == "social_media"

            # Step 4: Create tasks in orchestrator
            orch = TaskOrchestrator(workers=2)

            execution_log = []

            async def tracking_handler(task):
                execution_log.append({
                    "task_id": task.id,
                    "platform": task.platform,
                    "action": task.action,
                    "target": task.target,
                })
                # Record action in account manager
                am.record_action(acc.id, task.action, task.target)
                return {"status": "completed"}

            orch.register_handler("like", tracking_handler)
            orch.register_handler("follow", tracking_handler)

            orch.add_tasks([
                Task(id="int_like_1", platform="twitter", action="like",
                     target="https://twitter.com/post/1"),
                Task(id="int_like_2", platform="twitter", action="like",
                     target="https://twitter.com/post/2"),
                Task(id="int_follow_1", platform="twitter", action="follow",
                     target="https://twitter.com/user_x"),
            ])

            # Step 5: Execute
            results = await orch.run()

            # Verify all tasks completed
            assert len(results) == 3
            assert all(r.status == TaskStatus.SUCCESS for r in results)

            # Verify execution log
            assert len(execution_log) == 3

            # Verify account actions were recorded
            updated_acc = am.get_account(acc.id)
            assert updated_acc.total_actions == 3

            # Verify orchestrator stats
            stats = orch.stats
            assert stats["processed"] == 3
            assert stats["success"] == 3
            assert stats["failed"] == 0

        finally:
            self._cleanup(path)

    def test_account_lifecycle_with_fingerprint_rotation(self):
        """
        Simulate fingerprint rotation: when one account gets banned,
        create a new account with a different fingerprint.
        """
        am, path = self._make_db()
        try:
            # Create first account with fingerprint A
            fp_a = FingerprintManager.generate("rotation_user_v1", os="windows", browser="chrome")
            acc_a = am.create_account(
                platform="twitter",
                username="rotation_user",
                profile_id=fp_a.profile_id,
            )
            am.update_status(acc_a.id, AccountStatus.ACTIVE)

            # Simulate ban
            am.update_status(acc_a.id, AccountStatus.BANNED, reason="Detected as bot")
            assert am.get_account(acc_a.id).status == AccountStatus.BANNED

            # Create second account with fingerprint B (different OS for variety)
            fp_b = FingerprintManager.generate("rotation_user_v2", os="macos", browser="chrome")
            acc_b = am.create_account(
                platform="instagram",
                username="rotation_user",
                profile_id=fp_b.profile_id,
            )
            am.update_status(acc_b.id, AccountStatus.ACTIVE)

            # Verify fingerprints are different
            assert fp_a.user_agent != fp_b.user_agent
            assert fp_a.os != fp_b.os

            # Verify account B is available
            available = am.get_available_accounts("instagram")
            assert any(a.id == acc_b.id for a in available)

            # Verify account A is NOT available (banned)
            banned_available = am.get_available_accounts("twitter")
            assert not any(a.id == acc_a.id for a in banned_available)

        finally:
            self._cleanup(path)

    @pytest.mark.asyncio
    async def test_captcha_solver_integration_with_action_engine(self):
        """
        Simulate: ActionEngine encounters captcha → CaptchaSolver solves it.
        """
        page = self._make_mock_page()

        # Create solver
        solver = CaptchaSolver(api_key="integration_test_key", provider="2captcha")

        # Mock the HTTP flow
        mock_in_response = MagicMock()
        mock_in_response.json.return_value = {"status": 1, "request": "captcha_task_1"}

        mock_res_response = MagicMock()
        mock_res_response.json.return_value = {
            "status": 1,
            "request": "solved_token_abc123",
        }

        solver._client = AsyncMock()
        solver._client.post = AsyncMock(return_value=mock_in_response)
        solver._client.get = AsyncMock(return_value=mock_res_response)

        # Simulate solving captcha during action
        result = await solver.solve_recaptcha_v2(
            page, site_key="6Lc...integration", url="https://example.com"
        )

        assert result.success is True
        assert result.token == "solved_token_abc123"

        # Verify stats updated
        stats = solver.stats
        assert stats["solved"] == 1
        assert stats["failed"] == 0

    def test_behavior_profile_to_action_engine_integration(self):
        """
        Verify that BehaviorProfile parameters flow correctly into ActionEngine.
        """
        page = self._make_mock_page()

        for profile_name in ["casual_reader", "power_user", "researcher", "social_media"]:
            engine = ActionEngine(page, profile=profile_name)

            # Verify the behavior engine has the correct profile
            assert engine.behavior.profile.name == profile_name

            # Verify profile parameters are accessible
            assert engine.behavior.profile.mouse_move_min_ms > 0
            assert engine.behavior.profile.typing_speed_wpm[0] > 0

    @pytest.mark.asyncio
    async def test_human_behavior_with_action_engine_realistic_scenario(self):
        """
        Simulate a realistic browsing scenario:
        navigate → read page → scroll → click element.
        """
        page = self._make_mock_page()
        engine = ActionEngine(page, profile="casual_reader", seed=42)

        # Navigate
        nav = await engine.navigate("https://example.com")
        assert nav.is_success is True

        # Read page (simulates human reading behavior)
        read_result = await engine.view_content(duration_seconds=0.05)
        assert read_result.action_type == ActionType.VIEW

        # Scroll and read
        scroll_result = await engine.scroll_and_read(pages=0.05)
        assert scroll_result.action_type == ActionType.SCROLL

        # Verify all results tracked
        assert len(engine.results) == 3
        assert engine.success_count >= 1  # At least navigate
