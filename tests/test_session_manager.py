"""
Тесты для Session Manager модуля.

Покрытие:
- SessionData: создание, сериализация, TTL
- SessionManager: save/load/delete/list сессии
- Шифрование/дешифрование
- TTL expiration
- Cleanup
- Edge cases
"""
import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lab_playwright_kit.session_manager import (
    SessionData,
    SessionManager,
)


# ═══════════════════════════════════════════════════════════════════
# SessionData
# ═══════════════════════════════════════════════════════════════════

class TestSessionData:
    """Тесты SessionData dataclass."""

    def test_creation_defaults(self):
        """Создание с дефолтными значениями."""
        data = SessionData(name="test_session")
        assert data.name == "test_session"
        assert data.cookies == []
        assert data.local_storage == {}
        assert data.session_storage == {}
        assert data.url == ""
        assert data.ttl_seconds == 0
        assert data.metadata == {}

    def test_creation_full(self):
        """Полное создание."""
        data = SessionData(
            name="full_session",
            cookies=[{"name": "sid", "value": "abc123"}],
            local_storage={"theme": "dark"},
            session_storage={"token": "xyz"},
            url="https://example.com",
            ttl_seconds=3600,
            metadata={"user": "admin"},
        )
        assert data.name == "full_session"
        assert len(data.cookies) == 1
        assert data.local_storage["theme"] == "dark"
        assert data.session_storage["token"] == "xyz"
        assert data.url == "https://example.com"
        assert data.ttl_seconds == 3600
        assert data.metadata["user"] == "admin"

    def test_is_expired_no_ttl(self):
        """Сессия без TTL не истекает."""
        data = SessionData(name="no_ttl", ttl_seconds=0)
        assert data.is_expired is False

    def test_is_expired_within_ttl(self):
        """Сессия в пределах TTL не истекла."""
        data = SessionData(
            name="fresh",
            ttl_seconds=3600,
            updated_at=time.time(),
        )
        assert data.is_expired is False

    def test_is_expired_past_ttl(self):
        """Сессия за пределами TTL истекла."""
        data = SessionData(
            name="expired",
            ttl_seconds=60,
            updated_at=time.time() - 120,  # 2 минуты назад
        )
        assert data.is_expired is True

    def test_age_seconds(self):
        """Возраст сессии."""
        data = SessionData(
            name="aged",
            updated_at=time.time() - 100,
        )
        # Допуск на время выполнения теста
        assert 99 <= data.age_seconds <= 102

    def test_to_dict(self):
        """Сериализация в словарь."""
        data = SessionData(
            name="test",
            cookies=[{"name": "a"}],
            local_storage={"k": "v"},
            url="https://example.com",
            ttl_seconds=100,
        )
        d = data.to_dict()
        assert d["name"] == "test"
        assert d["cookies"] == [{"name": "a"}]
        assert d["local_storage"] == {"k": "v"}
        assert d["url"] == "https://example.com"
        assert d["ttl_seconds"] == 100

    def test_from_dict(self):
        """Десериализация из словаря."""
        raw = {
            "name": "restored",
            "cookies": [{"name": "sid"}],
            "local_storage": {"theme": "light"},
            "session_storage": {"token": "abc"},
            "url": "https://test.com",
            "created_at": 1000.0,
            "updated_at": 2000.0,
            "ttl_seconds": 500,
            "metadata": {"key": "val"},
        }
        data = SessionData.from_dict(raw)
        assert data.name == "restored"
        assert data.cookies == [{"name": "sid"}]
        assert data.local_storage == {"theme": "light"}
        assert data.session_storage == {"token": "abc"}
        assert data.url == "https://test.com"
        assert data.created_at == 1000.0
        assert data.updated_at == 2000.0
        assert data.ttl_seconds == 500
        assert data.metadata == {"key": "val"}

    def test_from_dict_defaults(self):
        """Десериализация с дефолтными значениями."""
        data = SessionData.from_dict({"name": "minimal"})
        assert data.name == "minimal"
        assert data.cookies == []
        assert data.ttl_seconds == 0

    def test_roundtrip_serialization(self):
        """Round-trip сериализация → десериализация."""
        original = SessionData(
            name="roundtrip",
            cookies=[{"name": "a", "value": "b"}],
            local_storage={"k1": "v1", "k2": "v2"},
            session_storage={"s1": "sv1"},
            url="https://roundtrip.com",
            ttl_seconds=7200,
            metadata={"test": True},
        )
        restored = SessionData.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.cookies == original.cookies
        assert restored.local_storage == original.local_storage
        assert restored.session_storage == original.session_storage
        assert restored.url == original.url
        assert restored.ttl_seconds == original.ttl_seconds
        assert restored.metadata == original.metadata


# ═══════════════════════════════════════════════════════════════════
# SessionManager — инициализация
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerInit:
    """Тесты инициализации SessionManager."""

    def test_init_creates_directory(self, tmp_path):
        """Инициализация создаёт директорию хранения."""
        storage = tmp_path / "sessions"
        SessionManager(str(storage))
        assert storage.exists()
        assert storage.is_dir()

    def test_init_with_encryption_key(self, tmp_path):
        """Инициализация с ключом шифрования."""
        manager = SessionManager(str(tmp_path), encryption_key="my-secret-key")
        assert manager._fernet is not None

    def test_init_without_encryption_key(self, tmp_path):
        """Инициализация без ключа — генерируется случайный."""
        manager = SessionManager(str(tmp_path))
        assert manager._fernet is not None

    def test_storage_dir_property(self, tmp_path):
        """Свойство storage_dir."""
        manager = SessionManager(str(tmp_path))
        assert manager.storage_dir == tmp_path


# ═══════════════════════════════════════════════════════════════════
# SessionManager — save/load с моками
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerSaveLoad:
    """Тесты save_session и load_session с моками."""

    @pytest.mark.asyncio
    async def test_save_session_basic(self, tmp_path):
        """Базовое сохранение сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "sid", "value": "abc123", "domain": "example.com"},
        ])

        mock_page = AsyncMock()
        mock_page.url = "https://example.com/dashboard"
        mock_page.evaluate = AsyncMock(side_effect=[
            {"theme": "dark"},  # localStorage
            {"token": "xyz"},   # sessionStorage
        ])
        mock_context.pages = [mock_page]

        result = await manager.save_session(mock_context, "test_session")

        assert result.name == "test_session"
        assert len(result.cookies) == 1
        assert result.cookies[0]["name"] == "sid"
        assert result.local_storage == {"theme": "dark"}
        assert result.session_storage == {"token": "xyz"}
        assert result.url == "https://example.com/dashboard"

    @pytest.mark.asyncio
    async def test_save_session_with_ttl(self, tmp_path):
        """Сохранение с TTL."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        result = await manager.save_session(
            mock_context, "ttl_session", ttl_seconds=3600
        )
        assert result.ttl_seconds == 3600

    @pytest.mark.asyncio
    async def test_save_session_with_metadata(self, tmp_path):
        """Сохранение с метаданными."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        result = await manager.save_session(
            mock_context,
            "meta_session",
            metadata={"user": "admin", "platform": "habr"},
        )
        assert result.metadata == {"user": "admin", "platform": "habr"}

    @pytest.mark.asyncio
    async def test_save_session_no_pages(self, tmp_path):
        """Сохранение без открытых страниц."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        result = await manager.save_session(mock_context, "no_pages")
        assert result.url == ""
        assert result.local_storage == {}
        assert result.session_storage == {}

    @pytest.mark.asyncio
    async def test_save_session_storage_error_fallback(self, tmp_path):
        """Сохранение при ошибке извлечения storage."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])

        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        mock_context.pages = [mock_page]

        result = await manager.save_session(mock_context, "error_session")
        assert result.local_storage == {}
        assert result.session_storage == {}

    @pytest.mark.asyncio
    async def test_load_session_basic(self, tmp_path):
        """Базовая загрузка сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        # Сначала сохранить
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "sid", "value": "abc123"},
        ])
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.evaluate = AsyncMock(return_value={})
        mock_context.pages = [mock_page]

        await manager.save_session(mock_context, "load_test")

        # Теперь загрузить
        mock_context2 = AsyncMock()
        mock_context2.clear_cookies = AsyncMock()
        mock_context2.add_cookies = AsyncMock()
        mock_page2 = AsyncMock()
        mock_page2.evaluate = AsyncMock()
        mock_context2.pages = [mock_page2]

        result = await manager.load_session(mock_context2, "load_test")
        assert result is not None
        assert result.name == "load_test"
        mock_context2.clear_cookies.assert_called_once()
        mock_context2.add_cookies.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_session_not_found(self, tmp_path):
        """Загрузка несуществующей сессии — None."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        result = await manager.load_session(mock_context, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_session_expired(self, tmp_path):
        """Загрузка истёкшей сессии — None."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        # Сохранить с TTL
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(
            mock_context, "expired_test", ttl_seconds=1
        )

        # Подождать истечения TTL
        await asyncio.sleep(1.5)

        mock_context2 = AsyncMock()
        result = await manager.load_session(mock_context2, "expired_test")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_session_restores_storage(self, tmp_path):
        """Згрузка восстанавливает localStorage и sessionStorage."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        # Сохранить
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.evaluate = AsyncMock(side_effect=[
            {"theme": "dark"},
            {"token": "xyz"},
        ])
        mock_context.pages = [mock_page]

        await manager.save_session(mock_context, "storage_test")

        # Загрузить
        mock_context2 = AsyncMock()
        mock_context2.clear_cookies = AsyncMock()
        mock_context2.add_cookies = AsyncMock()
        mock_page2 = AsyncMock()
        mock_page2.evaluate = AsyncMock()
        mock_context2.pages = [mock_page2]

        result = await manager.load_session(mock_context2, "storage_test")
        assert result is not None
        # evaluate вызывается для каждого ключа в storage
        assert mock_page2.evaluate.call_count >= 2


# ═══════════════════════════════════════════════════════════════════
# SessionManager — delete, list, exists
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerManagement:
    """Тесты управления сессиями."""

    @pytest.mark.asyncio
    async def test_delete_session(self, tmp_path):
        """Удаление сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "to_delete")
        assert manager.session_exists("to_delete") is True

        result = manager.delete_session("to_delete")
        assert result is True
        assert manager.session_exists("to_delete") is False

    def test_delete_nonexistent_session(self, tmp_path):
        """Удаление несуществующей сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        result = manager.delete_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_sessions(self, tmp_path):
        """Список сессий."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "session_a")
        await manager.save_session(mock_context, "session_b")

        sessions = manager.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert "session_a" in names
        assert "session_b" in names

    @pytest.mark.asyncio
    async def test_list_sessions_excludes_expired(self, tmp_path):
        """Список исключает истёкшие сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "fresh", ttl_seconds=3600)
        await manager.save_session(mock_context, "expired", ttl_seconds=1)

        await asyncio.sleep(1.5)

        sessions = manager.list_sessions(include_expired=False)
        names = {s["name"] for s in sessions}
        assert "fresh" in names
        assert "expired" not in names

    @pytest.mark.asyncio
    async def test_list_sessions_includes_expired(self, tmp_path):
        """Список включает истёкшие при include_expired=True."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "expired", ttl_seconds=1)
        await asyncio.sleep(1.5)

        sessions = manager.list_sessions(include_expired=True)
        assert len(sessions) == 1
        assert sessions[0]["is_expired"] is True

    def test_list_sessions_empty(self, tmp_path):
        """Пустой список сессий."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        sessions = manager.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_session_exists(self, tmp_path):
        """Проверка существования сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "existing")
        assert manager.session_exists("existing") is True
        assert manager.session_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_session_exists_expired(self, tmp_path):
        """Существование истёкшей сессии — False."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "expiring", ttl_seconds=1)
        await asyncio.sleep(1.5)

        assert manager.session_exists("expiring") is False


# ═══════════════════════════════════════════════════════════════════
# SessionManager — cleanup
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerCleanup:
    """Тесты очистки сессий."""

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, tmp_path):
        """Очистка истёкших сессий."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "keep", ttl_seconds=3600)
        await manager.save_session(mock_context, "remove1", ttl_seconds=1)
        await manager.save_session(mock_context, "remove2", ttl_seconds=1)

        await asyncio.sleep(1.5)

        removed = manager.cleanup_expired()
        assert removed == 2
        assert manager.session_exists("keep") is True
        assert manager.session_exists("remove1") is False
        assert manager.session_exists("remove2") is False

    def test_cleanup_no_expired(self, tmp_path):
        """Очистка без истёкших сессий."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        removed = manager.cleanup_expired()
        assert removed == 0


# ═══════════════════════════════════════════════════════════════════
# SessionManager — шифрование
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerEncryption:
    """Тесты шифрования сессий."""

    @pytest.mark.asyncio
    async def test_encryption_roundtrip(self, tmp_path):
        """Шифрование → дешифрование с одним ключом."""
        manager = SessionManager(str(tmp_path), encryption_key="secret-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "secret", "value": "data"},
        ])
        mock_page = AsyncMock()
        mock_page.url = "https://secure.com"
        mock_page.evaluate = AsyncMock(return_value={})
        mock_context.pages = [mock_page]

        await manager.save_session(mock_context, "encrypted")

        # Загрузить тем же менеджером
        mock_context2 = AsyncMock()
        mock_context2.clear_cookies = AsyncMock()
        mock_context2.add_cookies = AsyncMock()
        mock_page2 = AsyncMock()
        mock_page2.evaluate = AsyncMock()
        mock_context2.pages = [mock_page2]

        result = await manager.load_session(mock_context2, "encrypted")
        assert result is not None
        assert result.cookies[0]["value"] == "data"

    @pytest.mark.asyncio
    async def test_wrong_key_fails(self, tmp_path):
        """Загрузка с неправильным ключом — None."""
        # Сохранить с одним ключом
        manager1 = SessionManager(str(tmp_path), encryption_key="key1")
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []
        await manager1.save_session(mock_context, "wrong_key_test")

        # Попытаться загрузить другим ключом
        manager2 = SessionManager(str(tmp_path), encryption_key="key2")
        mock_context2 = AsyncMock()
        result = await manager2.load_session(mock_context2, "wrong_key_test")
        assert result is None

    @pytest.mark.asyncio
    async def test_data_encrypted_on_disk(self, tmp_path):
        """Данные на диске зашифрованы."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "secret", "value": "sensitive-data"},
        ])
        mock_context.pages = []

        await manager.save_session(mock_context, "disk_test")

        # Проверить что файл содержит зашифрованные данные
        enc_file = tmp_path / "disk_test.enc"
        assert enc_file.exists()
        raw_content = enc_file.read_bytes()
        # Зашифрованные данные не должны содержать plain-text
        assert b"sensitive-data" not in raw_content

        # Метаданные не содержат cookies
        meta_file = tmp_path / "disk_test.meta.json"
        meta = json.loads(meta_file.read_text())
        assert "cookies" not in meta
        assert "local_storage" not in meta


# ═══════════════════════════════════════════════════════════════════
# SessionManager — get_session_info
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerInfo:
    """Тесты get_session_info."""

    @pytest.mark.asyncio
    async def test_get_session_info(self, tmp_path):
        """Получение информации о сессии."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")

        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.pages = []

        await manager.save_session(mock_context, "info_test", ttl_seconds=3600)

        info = manager.get_session_info("info_test")
        assert info is not None
        assert info["name"] == "info_test"
        assert info["ttl_seconds"] == 3600
        assert info["is_expired"] is False

    def test_get_session_info_not_found(self, tmp_path):
        """Информация о несуществующей сессии — None."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        info = manager.get_session_info("nonexistent")
        assert info is None


# ═══════════════════════════════════════════════════════════════════
# SessionManager — валидация
# ═══════════════════════════════════════════════════════════════════

class TestSessionManagerValidation:
    """Тесты валидации входных данных."""

    def test_empty_name_raises(self, tmp_path):
        """Пустое имя сессии — ValueError."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        with pytest.raises(ValueError, match="empty"):
            manager._validate_name("")

    def test_whitespace_name_raises(self, tmp_path):
        """Имя из пробелов — ValueError."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        with pytest.raises(ValueError, match="empty"):
            manager._validate_name("   ")

    def test_forbidden_characters_raise(self, tmp_path):
        """Запрещённые символы в имени — ValueError."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        for char in '/\\:*?"<>|':
            with pytest.raises(ValueError, match="forbidden"):
                manager._validate_name(f"bad{char}test")

    def test_valid_names(self, tmp_path):
        """Валидные имена принимаются."""
        manager = SessionManager(str(tmp_path), encryption_key="test-key")
        valid_names = [
            "simple",
            "with-dash",
            "with_underscore",
            "with.dot",
            "CamelCase",
            "123numeric",
            "mixed-name_123.test",
        ]
        for name in valid_names:
            manager._validate_name(name)  # Не должно бросать исключение
