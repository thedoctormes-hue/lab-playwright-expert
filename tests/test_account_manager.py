"""
Тесты для AccountManager, Account, AccountStatus, Platform.

Покрывает:
  - Account: создание, is_available, cooldown_remaining, metadata
  - AccountStatus / Platform: enum значения
  - AccountManager: CRUD, ротация, статистика, шифрование
"""
import os
import tempfile
import time

import pytest

from lab_playwright_kit.account_manager import (
    Account,
    AccountManager,
    AccountStatus,
    Platform,
)


# ─── AccountStatus ───────────────────────────────────────────────────────────

class TestAccountStatus:
    """Тесты enum AccountStatus."""

    def test_all_statuses(self):
        expected = {"created", "warmup", "active", "cooldown", "banned", "dead"}
        actual = {s.value for s in AccountStatus}
        assert actual == expected

    def test_status_values(self):
        assert AccountStatus.CREATED == "created"
        assert AccountStatus.WARMUP == "warmup"
        assert AccountStatus.ACTIVE == "active"
        assert AccountStatus.COOLDOWN == "cooldown"
        assert AccountStatus.BANNED == "banned"
        assert AccountStatus.DEAD == "dead"


# ─── Platform ────────────────────────────────────────────────────────────────

class TestPlatform:
    """Тесты enum Platform."""

    def test_common_platforms(self):
        """Основные платформы определены."""
        assert Platform.TWITTER == "twitter"
        assert Platform.INSTAGRAM == "instagram"
        assert Platform.TELEGRAM == "telegram"
        assert Platform.HABR == "habr"
        assert Platform.VC_RU == "vcru"
        assert Platform.CUSTOM == "custom"

    def test_platform_count(self):
        """Не менее 16 платформ."""
        assert len(Platform) >= 16


# ─── Account ─────────────────────────────────────────────────────────────────

class TestAccount:
    """Тесты dataclass Account."""

    def test_default_creation(self):
        acc = Account()
        assert acc.id == 0
        assert acc.platform == ""
        assert acc.username == ""
        assert acc.status == AccountStatus.CREATED
        assert acc.total_actions == 0
        assert acc.daily_actions == 0
        assert acc.daily_limit == 100

    def test_custom_creation(self):
        acc = Account(
            id=1, platform="twitter", username="bot_001",
            status=AccountStatus.ACTIVE, daily_limit=50,
        )
        assert acc.id == 1
        assert acc.platform == "twitter"
        assert acc.daily_limit == 50

    def test_is_available_active(self):
        """ACTIVE аккаунт доступен."""
        acc = Account(status=AccountStatus.ACTIVE, daily_actions=0, daily_limit=100)
        assert acc.is_available is True

    def test_is_available_banned(self):
        """BANNED аккаунт недоступен."""
        acc = Account(status=AccountStatus.BANNED)
        assert acc.is_available is False

    def test_is_available_dead(self):
        """DEAD аккаунт недоступен."""
        acc = Account(status=AccountStatus.DEAD)
        assert acc.is_available is False

    def test_is_available_cooldown_active(self):
        """COOLDOWN с истёкшим сроком — доступен."""
        acc = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() - 100,  # Уже прошёл
        )
        assert acc.is_available is True

    def test_is_available_cooldown_not_expired(self):
        """COOLDOWN с неистёкшим сроком — недоступен."""
        acc = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() + 3600,  # Ещё час
        )
        assert acc.is_available is False

    def test_is_available_daily_limit_exceeded(self):
        """Превышен дневной лимит — недоступен."""
        acc = Account(status=AccountStatus.ACTIVE, daily_actions=100, daily_limit=100)
        assert acc.is_available is False

    def test_is_available_daily_limit_not_exceeded(self):
        """Дневной лимит не превышен — доступен."""
        acc = Account(status=AccountStatus.ACTIVE, daily_actions=99, daily_limit=100)
        assert acc.is_available is True

    def test_cooldown_remaining_zero_for_active(self):
        """cooldown_remaining = 0 для не-COOLDOWN."""
        acc = Account(status=AccountStatus.ACTIVE)
        assert acc.cooldown_remaining == 0

    def test_cooldown_remaining_positive(self):
        """cooldown_remaining > 0 для активного COOLDOWN."""
        acc = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() + 3600,
        )
        assert acc.cooldown_remaining > 0
        assert acc.cooldown_remaining <= 3600

    def test_cooldown_remaining_expired(self):
        """cooldown_remaining = 0 для истёкшего COOLDOWN."""
        acc = Account(
            status=AccountStatus.COOLDOWN,
            cooldown_until=time.time() - 100,
        )
        assert acc.cooldown_remaining == 0

    def test_metadata_empty(self):
        """metadata для пустого metadata_json."""
        acc = Account(metadata_json="{}")
        assert acc.metadata == {}

    def test_metadata_parsed(self):
        """metadata парсит JSON."""
        acc = Account(metadata_json='{"key": "value", "num": 42}')
        assert acc.metadata == {"key": "value", "num": 42}

    def test_metadata_invalid_json(self):
        """metadata при невалидном JSON — пустой dict."""
        acc = Account(metadata_json="not json{{{")
        assert acc.metadata == {}


# ─── AccountManager ─────────────────────────────────────────────────────────

@pytest.fixture
def db_path():
    """Временная БД для тестов."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def manager(db_path):
    """AccountManager с временной БД."""
    mgr = AccountManager(db_path=db_path)
    yield mgr
    mgr.close()


class TestAccountManagerCRUD:
    """Тесты CRUD операций."""

    def test_create_account(self, manager):
        """Создание аккаунта."""
        acc = manager.create_account("twitter", username="bot_001", email="b@test.com")
        assert acc.id > 0
        assert acc.platform == "twitter"
        assert acc.username == "bot_001"
        assert acc.email == "b@test.com"
        assert acc.status == AccountStatus.CREATED

    def test_create_duplicate_raises(self, manager):
        """Дубликат — ValueError."""
        manager.create_account("twitter", username="dup_001")
        with pytest.raises(ValueError, match="already exists"):
            manager.create_account("twitter", username="dup_001")

    def test_create_with_all_fields(self, manager):
        """Создание со всеми полями."""
        acc = manager.create_account(
            "instagram",
            username="full_001",
            email="full@test.com",
            password="secret123",
            phone="+79991234567",
            proxy_url="socks5://127.0.0.1:1080",
            profile_id="fp_001",
            daily_limit=50,
            tags="bot,auto",
            metadata={"source": "test"},
        )
        assert acc.id > 0
        assert acc.proxy_url == "socks5://127.0.0.1:1080"
        assert acc.profile_id == "fp_001"
        assert acc.daily_limit == 50
        assert acc.tags == "bot,auto"

    def test_get_account(self, manager):
        """Получение аккаунта по ID."""
        created = manager.create_account("twitter", username="get_001")
        fetched = manager.get_account(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.username == "get_001"

    def test_get_account_not_found(self, manager):
        """Получение несуществующего аккаунта."""
        assert manager.get_account(99999) is None

    def test_get_account_by_username(self, manager):
        """Получение по платформе и имени."""
        manager.create_account("twitter", username="byname_001")
        acc = manager.get_account_by_username("twitter", "byname_001")
        assert acc is not None
        assert acc.username == "byname_001"

    def test_get_account_by_username_not_found(self, manager):
        """Получение несуществующего по имени."""
        assert manager.get_account_by_username("twitter", "nonexistent") is None

    def test_delete_account(self, manager):
        """Удаление аккаунта."""
        acc = manager.create_account("twitter", username="del_001")
        assert manager.delete_account(acc.id) is True
        assert manager.get_account(acc.id) is None

    def test_delete_nonexistent(self, manager):
        """Удаление несуществующего."""
        assert manager.delete_account(99999) is False


class TestAccountManagerQuery:
    """Тесты запросов аккаунтов."""

    def test_get_accounts_all(self, manager):
        """Получение всех аккаунтов."""
        manager.create_account("twitter", username="q_001")
        manager.create_account("instagram", username="q_002")
        accounts = manager.get_accounts()
        assert len(accounts) == 2

    def test_get_accounts_by_platform(self, manager):
        """Фильтр по платформе."""
        manager.create_account("twitter", username="pf_001")
        manager.create_account("twitter", username="pf_002")
        manager.create_account("instagram", username="pf_003")
        accounts = manager.get_accounts(platform="twitter")
        assert len(accounts) == 2

    def test_get_accounts_by_status(self, manager):
        """Фильтр по статусу."""
        acc = manager.create_account("twitter", username="st_001")
        manager.update_status(acc.id, AccountStatus.ACTIVE)
        manager.create_account("twitter", username="st_002")
        accounts = manager.get_accounts(status=AccountStatus.ACTIVE)
        assert len(accounts) == 1
        assert accounts[0].username == "st_001"

    def test_get_accounts_by_tags(self, manager):
        """Фильтр по тегам."""
        manager.create_account("twitter", username="tag_001", tags="bot,auto")
        manager.create_account("twitter", username="tag_002", tags="manual")
        accounts = manager.get_accounts(tags="bot")
        assert len(accounts) == 1
        assert accounts[0].username == "tag_001"

    def test_get_accounts_limit(self, manager):
        """Лимит количества."""
        for i in range(5):
            manager.create_account("twitter", username=f"lim_{i:03d}")
        accounts = manager.get_accounts(limit=3)
        assert len(accounts) == 3

    def test_get_available_accounts(self, manager):
        """Доступные аккаунты."""
        acc = manager.create_account("twitter", username="avail_001")
        manager.update_status(acc.id, AccountStatus.ACTIVE)
        manager.create_account("twitter", username="avail_002")  # CREATED
        available = manager.get_available_accounts("twitter")
        assert len(available) == 1
        assert available[0].username == "avail_001"

    def test_get_next_account_round_robin(self, manager):
        """Round-robin: выбирает с наименьшим daily_actions."""
        acc1 = manager.create_account("twitter", username="rr_001")
        manager.update_status(acc1.id, AccountStatus.ACTIVE)
        acc2 = manager.create_account("twitter", username="rr_002")
        manager.update_status(acc2.id, AccountStatus.ACTIVE)
        manager.record_action(acc1.id, "like")
        next_acc = manager.get_next_account("twitter")
        assert next_acc is not None
        assert next_acc.username == "rr_002"  # Меньше действий

    def test_get_next_account_none(self, manager):
        """Нет доступных — None."""
        assert manager.get_next_account("twitter") is None


class TestAccountManagerStatus:
    """Тесты управления статусом."""

    def test_update_status(self, manager):
        """Обновление статуса."""
        acc = manager.create_account("twitter", username="ust_001")
        assert manager.update_status(acc.id, AccountStatus.ACTIVE) is True
        updated = manager.get_account(acc.id)
        assert updated.status == AccountStatus.ACTIVE

    def test_update_status_not_found(self, manager):
        """Обновление несуществующего."""
        assert manager.update_status(99999, AccountStatus.ACTIVE) is False

    def test_update_status_cooldown(self, manager):
        """Установка COOLDOWN заполняет cooldown_until."""
        acc = manager.create_account("twitter", username="uc_001")
        manager.update_status(acc.id, AccountStatus.COOLDOWN)
        updated = manager.get_account(acc.id)
        assert updated.status == AccountStatus.COOLDOWN
        assert updated.cooldown_until > time.time()

    def test_update_status_banned(self, manager):
        """Установка BANNED с причиной."""
        acc = manager.create_account("twitter", username="ub_001")
        manager.update_status(acc.id, AccountStatus.BANNED, reason="spam")
        updated = manager.get_account(acc.id)
        assert updated.status == AccountStatus.BANNED
        assert updated.ban_reason == "spam"


class TestAccountManagerActions:
    """Тесты записи действий."""

    def test_record_action(self, manager):
        """Запись действия обновляет счётчики."""
        acc = manager.create_account("twitter", username="ra_001")
        manager.record_action(acc.id, "like", target="https://t.co/abc")
        updated = manager.get_account(acc.id)
        assert updated.total_actions == 1
        assert updated.daily_actions == 1
        assert updated.last_action_at > 0

    def test_record_action_multiple(self, manager):
        """Несколько действий."""
        acc = manager.create_account("twitter", username="ra_002")
        for _ in range(5):
            manager.record_action(acc.id, "like")
        updated = manager.get_account(acc.id)
        assert updated.total_actions == 5
        assert updated.daily_actions == 5

    def test_reset_daily_counters(self, manager):
        """Сброс дневных счётчиков."""
        acc = manager.create_account("twitter", username="rdc_001")
        manager.record_action(acc.id, "like")
        manager.record_action(acc.id, "like")
        assert manager.reset_daily_counters() == 1
        updated = manager.get_account(acc.id)
        assert updated.daily_actions == 0
        assert updated.total_actions == 2  # total не сбрасывается

    def test_reset_daily_counters_empty(self, manager):
        """Сброс без активных счётчиков."""
        assert manager.reset_daily_counters() == 0

    def test_set_cooldown(self, manager):
        """Установка cooldown через set_cooldown."""
        acc = manager.create_account("twitter", username="sc_001")
        manager.set_cooldown(acc.id, hours=2.0)
        updated = manager.get_account(acc.id)
        assert updated.status == AccountStatus.COOLDOWN
        assert updated.cooldown_until > time.time() + 7000  # ~2h

    def test_get_action_history(self, manager):
        """История действий."""
        acc = manager.create_account("twitter", username="ah_001")
        manager.record_action(acc.id, "like", target="https://t.co/abc")
        manager.record_action(acc.id, "follow", target="@user")
        history = manager.get_action_history(acc.id)
        assert len(history) == 2
        # Последное действие первое (DESC)
        assert history[0]["action_type"] == "follow"
        assert history[1]["action_type"] == "like"


class TestAccountManagerStats:
    """Тесты статистики."""

    def test_get_stats_empty(self, manager):
        """Статистика пустой БД."""
        stats = manager.get_stats()
        assert stats["total"] == 0
        assert stats["total_actions"] == 0
        assert stats["platform"] == "all"

    def test_get_stats_with_accounts(self, manager):
        """Статистика с аккаунтами."""
        manager.create_account("twitter", username="gs_001")
        manager.create_account("twitter", username="gs_002")
        manager.create_account("instagram", username="gs_003")
        stats = manager.get_stats()
        assert stats["total"] == 3
        assert stats["by_status"]["created"] == 3

    def test_get_stats_by_platform(self, manager):
        """Статистика по платформе."""
        manager.create_account("twitter", username="gsp_001")
        manager.create_account("twitter", username="gsp_002")
        manager.create_account("instagram", username="gsp_003")
        stats = manager.get_stats(platform="twitter")
        assert stats["total"] == 2
        assert stats["platform"] == "twitter"

    def test_get_stats_with_actions(self, manager):
        """Статистика с действиями."""
        acc = manager.create_account("twitter", username="gsa_001")
        manager.record_action(acc.id, "like")
        manager.record_action(acc.id, "follow")
        stats = manager.get_stats(platform="twitter")
        assert stats["total_actions"] == 2


class TestAccountManagerEncryption:
    """Тесты шифрования паролей."""

    def test_encrypt_decrypt_roundtrip(self, manager):
        """Шифрование/дешифрование — roundtrip."""
        password = "my_secret_password_123"
        encrypted = manager._encrypt(password)
        assert encrypted != password
        decrypted = manager._decrypt(encrypted)
        assert decrypted == password

    def test_encrypt_empty(self, manager):
        """Шифрование пустой строки."""
        encrypted = manager._encrypt("")
        decrypted = manager._decrypt(encrypted)
        assert decrypted == ""

    def test_encrypt_special_chars(self, manager):
        """Шифрование спецсимволов."""
        password = "p@$$w0rd!#%^&*()"
        encrypted = manager._encrypt(password)
        decrypted = manager._decrypt(encrypted)
        assert decrypted == password

    def test_get_password(self, manager):
        """get_password расшифровывает пароль."""
        acc = manager.create_account("twitter", username="gp_001", password="secret123")
        assert manager.get_password(acc) == "secret123"

    def test_decrypt_invalid(self, manager):
        """Расшифровка невалидных данных."""
        result = manager._decrypt("not-valid-base64!!!")
        assert result == ""
