"""
Session Manager модуль: управление браузерными сессиями.

Поддерживает:
  - Сохранение/загрузку cookies, localStorage, sessionStorage
  - Шифрование сессий через Fernet (из cryptography)
  - TTL (time-to-live) для автоматического устаревания сессий
  - Хранение в файловой системе с метаданными

Example:
    >>> manager = SessionManager(storage_dir="/tmp/sessions")
    >>> await manager.save_session(page, "user_session")
    >>> await manager.load_session(page, "user_session")
    >>> sessions = manager.list_sessions()
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from playwright.async_api import BrowserContext


@dataclass
class SessionData:
    """Данные сессии для сериализации.

    Attributes:
        name: Имя сессии
        cookies: Список cookies
        local_storage: Данные localStorage {key: value}
        session_storage: Данные sessionStorage {key: value}
        url: URL страницы на момент сохранения
        created_at: Timestamp создания
        updated_at: Timestamp последнего обновления
        ttl_seconds: Время жизни сессии в секундах (0 = бессрочно)
        metadata: Произвольные метаданные
    """

    name: str
    cookies: list[dict[str, Any]] = field(default_factory=list)
    local_storage: dict[str, str] = field(default_factory=dict)
    session_storage: dict[str, str] = field(default_factory=dict)
    url: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_seconds: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Проверить, истекла ли сессия."""
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.updated_at) > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Возраст сессии в секундах."""
        return time.time() - self.updated_at

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "name": self.name,
            "cookies": self.cookies,
            "local_storage": self.local_storage,
            "session_storage": self.session_storage,
            "url": self.url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl_seconds": self.ttl_seconds,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        """Десериализация из словаря."""
        return cls(
            name=data.get("name", ""),
            cookies=data.get("cookies", []),
            local_storage=data.get("local_storage", {}),
            session_storage=data.get("session_storage", {}),
            url=data.get("url", ""),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            ttl_seconds=data.get("ttl_seconds", 0),
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Менеджер браузерных сессий.

    Сохраняет и восстанавливает cookies, localStorage, sessionStorage.
    Данные шифруются через Fernet. Поддерживает TTL для автоматического
    устаревания сессий.

    Example:
        >>> manager = SessionManager("/tmp/sessions", encryption_key="my-secret")
        >>> await manager.save_session(page, "habr", ttl_seconds=3600)
        >>> exists = manager.session_exists("habr")
        >>> if exists:
        ...     await manager.load_session(page, "habr")
        >>> sessions = manager.list_sessions()
        >>> manager.delete_session("habr")
    """

    def __init__(
        self,
        storage_dir: str = "/tmp/playwright_sessions",
        encryption_key: str | None = None,
    ):
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        # Генерация или использование предоставленного ключа
        if encryption_key:
            # Ключ должен быть 32-byte base64-encoded для Fernet
            # Если строка не в формате base64 — хешируем до 32 байт
            import base64
            import hashlib

            key_bytes = encryption_key.encode("utf-8")
            # SHA-256 → 32 байта → base64 = валидный Fernet key
            digest = hashlib.sha256(key_bytes).digest()
            fernet_key = base64.urlsafe_b64encode(digest)
            self._fernet = Fernet(fernet_key)
        else:
            self._fernet = Fernet(Fernet.generate_key())
            logger.warning(
                "No encryption key provided — generated random key. "
                "Sessions will not be recoverable after restart."
            )

    async def save_session(
        self,
        context: BrowserContext,
        name: str,
        ttl_seconds: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> SessionData:
        """Сохранить текущую сессию браузера.

        Извлекает cookies, localStorage и sessionStorage из контекста
        и сохраняет в зашифрованном виде.

        Args:
            context: Playwright BrowserContext
            name: Имя сессии (используется как имя файла)
            ttl_seconds: Время жизни сессии в секундах (0 = бессрочно)
            metadata: Произвольные метаданные

        Returns:
            SessionData с сохранёнными данными

        Raises:
            ValueError: Если name пустое или содержит недопустимые символы
        """
        self._validate_name(name)

        # Извлечь cookies
        cookies = await context.cookies()

        # Извлечь localStorage и sessionStorage из всех страниц
        local_storage: dict[str, str] = {}
        session_storage: dict[str, str] = {}
        url = ""

        pages = context.pages
        if pages:
            page = pages[0]
            url = page.url

            try:
                local_storage = await page.evaluate(
                    "() => { const d = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); d[k] = localStorage.getItem(k); } return d; }"
                )
            except Exception as e:
                logger.debug(f"Could not extract localStorage: {e}")

            try:
                session_storage = await page.evaluate(
                    "() => { const d = {}; for (let i = 0; i < sessionStorage.length; i++) { const k = sessionStorage.key(i); d[k] = sessionStorage.getItem(k); } return d; }"
                )
            except Exception as e:
                logger.debug(f"Could not extract sessionStorage: {e}")

        # Проверить, существует ли сессия — сохранить created_at
        existing = self._load_from_disk(name)
        created_at = existing.created_at if existing else time.time()

        session_data = SessionData(
            name=name,
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            url=url,
            created_at=created_at,
            updated_at=time.time(),
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )

        self._save_to_disk(session_data)
        logger.info(
            f"Session saved: {name} "
            f"({len(cookies)} cookies, {len(local_storage)} ls, "
            f"{len(session_storage)} ss, ttl={ttl_seconds}s)"
        )
        return session_data

    async def load_session(
        self,
        context: BrowserContext,
        name: str,
    ) -> SessionData | None:
        """Загрузить сессию в контекст браузера.

        Восстанавливает cookies, localStorage и sessionStorage
        из сохранённой сессии.

        Args:
            context: Playwright BrowserContext
            name: Имя сессии

        Returns:
            SessionData если сессия найдена и не истекла, иначе None

        Raises:
            ValueError: Если name пустое
        """
        self._validate_name(name)

        session_data = self._load_from_disk(name)
        if session_data is None:
            logger.warning(f"Session not found: {name}")
            return None

        if session_data.is_expired:
            logger.warning(
                f"Session expired: {name} "
                f"(age={session_data.age_seconds:.0f}s, "
                f"ttl={session_data.ttl_seconds}s)"
            )
            return None

        # Восстановить cookies
        if session_data.cookies:
            # Очистить существующие куки перед загрузкой
            await context.clear_cookies()
            try:
                await context.add_cookies(session_data.cookies)
            except Exception as e:
                logger.warning(f"Failed to restore some cookies: {e}")

        # Восстановить localStorage и sessionStorage
        pages = context.pages
        if pages and (session_data.local_storage or session_data.session_storage):
            page = pages[0]
            try:
                for key, value in session_data.local_storage.items():
                    await page.evaluate(
                        f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
                    )
                for key, value in session_data.session_storage.items():
                    await page.evaluate(
                        f"sessionStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
                    )
            except Exception as e:
                logger.warning(f"Failed to restore storage: {e}")

        logger.info(
            f"Session loaded: {name} "
            f"({len(session_data.cookies)} cookies, "
            f"{len(session_data.local_storage)} ls, "
            f"{len(session_data.session_storage)} ss)"
        )
        return session_data

    def delete_session(self, name: str) -> bool:
        """Удалить сохранённую сессию.

        Args:
            name: Имя сессии

        Returns:
            True если сессия была найдена и удалена
        """
        self._validate_name(name)

        session_file = self._session_path(name)
        meta_file = self._meta_path(name)

        deleted = False
        if session_file.exists():
            session_file.unlink()
            deleted = True
        if meta_file.exists():
            meta_file.unlink()

        if deleted:
            logger.info(f"Session deleted: {name}")
        else:
            logger.warning(f"Session not found for deletion: {name}")

        return deleted

    def list_sessions(self, include_expired: bool = False) -> list[dict[str, Any]]:
        """Получить список всех сохранённых сессий.

        Args:
            include_expired: Включить истёкшие сессии

        Returns:
            Список словарей с информацией о сессиях:
            [{name, created_at, updated_at, ttl_seconds, is_expired, url}]
        """
        sessions: list[dict[str, Any]] = []

        for meta_file in sorted(self._storage_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                is_expired = (
                    meta.get("ttl_seconds", 0) > 0
                    and (time.time() - meta.get("updated_at", 0)) > meta["ttl_seconds"]
                )

                if not include_expired and is_expired:
                    continue

                sessions.append(
                    {
                        "name": meta.get("name", ""),
                        "created_at": meta.get("created_at", 0),
                        "updated_at": meta.get("updated_at", 0),
                        "ttl_seconds": meta.get("ttl_seconds", 0),
                        "is_expired": is_expired,
                        "url": meta.get("url", ""),
                    }
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Corrupted session metadata: {meta_file}: {e}")

        return sessions

    def session_exists(self, name: str) -> bool:
        """Проверить существование сессии.

        Args:
            name: Имя сессии

        Returns:
            True если сессия существует и не истекла
        """
        session_data = self._load_from_disk(name)
        if session_data is None:
            return False
        if session_data.is_expired:
            return False
        return True

    def cleanup_expired(self) -> int:
        """Удалить все истёкшие сессии.

        Returns:
            Количество удалённых сессий
        """
        removed = 0
        for meta_file in list(self._storage_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                ttl = meta.get("ttl_seconds", 0)
                updated = meta.get("updated_at", 0)
                if ttl > 0 and (time.time() - updated) > ttl:
                    name = meta.get("name", "")
                    if self.delete_session(name):
                        removed += 1
            except (json.JSONDecodeError, KeyError):
                # Повреждённый файл — удалить
                meta_file.unlink(missing_ok=True)
                session_file = meta_file.with_suffix("").with_suffix(".enc")
                session_file.unlink(missing_ok=True)
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} expired/corrupted sessions")
        return removed

    def get_session_info(self, name: str) -> dict[str, Any] | None:
        """Получить информацию о сессии без расшифровки данных.

        Args:
            name: Имя сессии

        Returns:
            Словарь с метаданными сессии или None
        """
        meta_file = self._meta_path(name)
        if not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            ttl = meta.get("ttl_seconds", 0)
            updated = meta.get("updated_at", 0)
            meta["is_expired"] = ttl > 0 and (time.time() - updated) > ttl
            return meta
        except (json.JSONDecodeError, KeyError):
            return None

    @property
    def storage_dir(self) -> Path:
        """Директория хранения сессий."""
        return self._storage_dir

    # ─── Internal methods ──────────────────────────────────────────────────────

    def _session_path(self, name: str) -> Path:
        """Путь к файлу зашифрованных данных сессии."""
        return self._storage_dir / f"{name}.enc"

    def _meta_path(self, name: str) -> Path:
        """Путь к файлу метаданных сессии."""
        return self._storage_dir / f"{name}.meta.json"

    def _save_to_disk(self, session_data: SessionData) -> None:
        """Сохранить сессию на диск (зашифрованно)."""
        # Сохранить метаданные (незашифрованно — для list_sessions)
        meta = session_data.to_dict()
        # Не сохраняем cookies в метаданные — они чувствительные
        meta.pop("cookies")
        meta.pop("local_storage")
        meta.pop("session_storage")

        meta_file = self._meta_path(session_data.name)
        meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Сохранить полные данные зашифрованно
        plaintext = json.dumps(session_data.to_dict(), ensure_ascii=False).encode("utf-8")
        encrypted = self._fernet.encrypt(plaintext)

        session_file = self._session_path(session_data.name)
        session_file.write_bytes(encrypted)

    def _load_from_disk(self, name: str) -> SessionData | None:
        """Загрузить сессию с диска (расшифровать)."""
        session_file = self._session_path(name)
        if not session_file.exists():
            return None

        try:
            encrypted = session_file.read_bytes()
            plaintext = self._fernet.decrypt(encrypted)
            data = json.loads(plaintext.decode("utf-8"))
            return SessionData.from_dict(data)
        except InvalidToken:
            logger.error(f"Session decryption failed: {name} (wrong key?)")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Session data corrupted: {name}: {e}")
            return None

    @staticmethod
    def _validate_name(name: str) -> None:
        """Валидация имени сессии.

        Args:
            name: Имя сессии

        Raises:
            ValueError: Если имя пустое или содержит недопустимые символы
        """
        if not name or not name.strip():
            raise ValueError("Session name cannot be empty")

        # Запретить символы, опасные для файловой системы
        forbidden = set("/\\:*?\"<>|")
        if any(c in forbidden for c in name):
            raise ValueError(
                f"Session name contains forbidden characters: {forbidden}"
            )
