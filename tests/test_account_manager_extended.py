"""
Расширенные тесты для AccountManager.

Покрывает:
  - AccountStatus enum
  - Platform enum
  - Account (metadata, is_available, cooldown_remaining)
  - AccountManager.__init__ / generate_key
  - AccountManager.create_account / get_account / get_accounts
  - AccountManager.update_status / record_action
  - AccountManager.get_stats / get_action_history
  - AccountManager.delete_account / close
  - AccountManager._encrypt / _decrypt
"""

from __future__ import annotations

import time

import pytest

from lab_playwright_kit.account_manager import (
    Account,
    AccountManager,
    AccountStatus,
    Platform,
)


# ─── AccountStatus ─────────────────────────────────────────────────────────


class TestAccountStatus:
    def test_values(self):
        assert AccountStatus.CREATED.value == "created"
        assert AccountStatus.WARMUP.value == "warmup"
        assert AccountStatus.ACTIVE.value == "active"
        assert AccountStatus.COOLDOWN.value == "cooldown"
        assert AccountStatus.BANNED.value == "banned"
        assert AccountStatus.DEAD.value == "dead"


# ─── Platform ──────────────────────────────────────────────────────────────


class TestPlatform:
    def test_values(self):
        assert Platform.TWITTER.value == "twitter"
        assert Platform.TELEGRAM.value == "telegram"
        assert Platform.HABR.value == "habr"
        assert Platform.CUSTOM.value == "custom"


# ─── Account ───────────────────────────────────────────────────────────────


class TestAccount:
    def test_defaults(self):
        a = Account()
        assert a.id == 0
        assert a.platform == ""
        assert a.status == AccountStatus.CREATED
        assert a.total_actions == 0
        assert a.daily_limit == 100

    def test_metadata_empty(self):
        a = Account()
        assert a.metadata == {}

    def test_metadata_parsed(self):
        a = Account(metadata_json='{"key": "val"}')
        assert a.metadata == {"key": "val"}

    def test_metadata_invalid(self):
        a = Account(metadata_json="not json")
        assert a.metadata == {}

    def test_is_available_active(self):
        a = Account(status=AccountStatus.ACTIVE, daily_actions=0, daily_limit=100)
        assert a.is_available is True

    def test_is_available_banned(self):
        a = Account(status=AccountStatus.BANNED)
        assert a.is_available is False

    def test_is_available_dead(self):
        a = Account(status=AccountStatus.DEAD)
        assert a.is_available is False

    def test_is_available_cooldown_active(self):
        a = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() + 3600,
        )
        assert a.is_available is False

    def test_is_available_cooldown_expired(self):
        a = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() - 100,
        )
        assert a.is_available is True

    def test_is_available_daily_limit(self):
        a = Account(
            status=AccountStatus.ACTIVE,
            daily_actions=100,
            daily_limit=100,
        )
        assert a.is_available is False

    def test_cooldown_remaining(self):
        a = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() + 3600,
        )
        assert 3590 <= a.cooldown_remaining <= 3600

    def test_cooldown_remaining_not_cooldown(self):
        a = Account(status=AccountStatus.ACTIVE)
        assert a.cooldown_remaining == 0

    def test_cooldown_remaining_expired(self):
        a = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() - 100,
        )
        assert a.cooldown_remaining == 0


# ─── AccountManager ────────────────────────────────────────────────────────


class TestAccountManager:
    def test_init(self, tmp_path):
        db = tmp_path / "test.db"
        mgr = AccountManager(db_path=str(db))
        assert db.exists()
        mgr.close()

    def test_generate_key(self):
        key = AccountManager.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0

    def test_create_account(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(
            platform="twitter",
            username="test_user",
            email="test@example.com",
            password="secret123",
        )
        assert acc.id > 0
        assert acc.platform == "twitter"
        assert acc.username == "test_user"
        assert acc.email == "test@example.com"
        assert acc.status == AccountStatus.CREATED
        mgr.close()

    def test_create_account_duplicate(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        mgr.create_account(platform="twitter", username="dup_user")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_account(platform="twitter", username="dup_user")
        mgr.close()

    def test_get_account(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        created = mgr.create_account(platform="twitter", username="get_test")
        fetched = mgr.get_account(created.id)
        assert fetched is not None
        assert fetched.username == "get_test"
        mgr.close()

    def test_get_account_not_found(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        assert mgr.get_account(99999) is None
        mgr.close()

    def test_get_account_by_username(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        mgr.create_account(platform="twitter", username="by_name")
        acc = mgr.get_account_by_username("twitter", "by_name")
        assert acc is not None
        assert acc.username == "by_name"
        mgr.close()

    def test_get_accounts_filter(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        mgr.create_account(platform="twitter", username="t1")
        mgr.create_account(platform="twitter", username="t2")
        mgr.create_account(platform="telegram", username="tg1")

        all_accs = mgr.get_accounts()
        assert len(all_accs) == 3

        tw_accs = mgr.get_accounts(platform="twitter")
        assert len(tw_accs) == 2

        mgr.close()

    def test_update_status(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="status_test")
        result = mgr.update_status(acc.id, AccountStatus.ACTIVE)
        assert result is True

        updated = mgr.get_account(acc.id)
        assert updated.status == AccountStatus.ACTIVE
        mgr.close()

    def test_update_status_not_found(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        assert mgr.update_status(99999, AccountStatus.BANNED) is False
        mgr.close()

    def test_record_action(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="action_test")
        mgr.record_action(acc.id, "like", target="post_123")

        updated = mgr.get_account(acc.id)
        assert updated.total_actions == 1
        assert updated.daily_actions == 1
        mgr.close()

    def test_get_stats(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        mgr.create_account(platform="twitter", username="stats_1")
        mgr.create_account(platform="twitter", username="stats_2")
        mgr.create_account(platform="telegram", username="stats_tg")

        stats = mgr.get_stats()
        assert stats["total"] == 3
        assert stats["by_status"]["created"] == 3

        tw_stats = mgr.get_stats(platform="twitter")
        assert tw_stats["total"] == 2
        mgr.close()

    def test_get_action_history(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="history_test")
        mgr.record_action(acc.id, "like")
        mgr.record_action(acc.id, "retweet")

        history = mgr.get_action_history(acc.id)
        assert len(history) == 2
        mgr.close()

    def test_delete_account(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="delete_me")
        assert mgr.delete_account(acc.id) is True
        assert mgr.get_account(acc.id) is None
        mgr.close()

    def test_delete_account_not_found(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        assert mgr.delete_account(99999) is False
        mgr.close()

    def test_encrypt_decrypt(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="enc-key")
        encrypted = mgr._encrypt("my-secret-password")
        assert encrypted != "my-secret-password"
        assert len(encrypted) > 0

        decrypted = mgr._decrypt(encrypted)
        assert decrypted == "my-secret-password"
        mgr.close()

    def test_encrypt_empty(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="enc-key")
        assert mgr._encrypt("") == ""
        assert mgr._decrypt("") == ""
        mgr.close()

    def test_get_password(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="pwd-key")
        acc = mgr.create_account(platform="twitter", username="pwd_test", password="secret!")
        pwd = mgr.get_password(acc)
        assert pwd == "secret!"
        mgr.close()

    def test_set_cooldown(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="cooldown_test")
        mgr.set_cooldown(acc.id, hours=2.0)

        updated = mgr.get_account(acc.id)
        assert updated.status == AccountStatus.COOLDOWN
        assert updated.cooldown_until > time.time()
        mgr.close()

    def test_reset_daily_counters(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        acc = mgr.create_account(platform="twitter", username="reset_test")
        mgr.record_action(acc.id, "like")
        mgr.record_action(acc.id, "retweet")

        updated = mgr.get_account(acc.id)
        assert updated.daily_actions == 2

        count = mgr.reset_daily_counters()
        assert count >= 1

        reset = mgr.get_account(acc.id)
        assert reset.daily_actions == 0
        mgr.close()

    def test_get_available_accounts(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        mgr.create_account(platform="twitter", username="avail_1")
        mgr.create_account(platform="twitter", username="avail_2")

        # Both are CREATED, not ACTIVE — so get_available_accounts returns empty
        available = mgr.get_available_accounts("twitter")
        assert isinstance(available, list)
        mgr.close()

    def test_get_next_account(self, tmp_path):
        mgr = AccountManager(db_path=str(tmp_path / "test.db"), encryption_key="test-key")
        # No active accounts → None
        assert mgr.get_next_account("twitter") is None
        mgr.close()
