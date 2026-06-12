"""
Account Manager — управление аккаунтами для браузерной автоматизации.

Жизненный цикл аккаунта:
  1. CREATE — создание нового аккаунта
  2. WARMUP — прогрев (имитация обычного пользователя)
  3. ACTIVE — активное использование
  4. COOLDOWN — пауза (чтобы не забанили)
  5. BANNED — заблокирован
  6. DEAD — не подлежит восстановлению

Хранение: SQLite с шифрованием чувствительных данных (Fernet / AES-128-CBC).

Использование:
    >>> manager = AccountManager(db_path="/tmp/accounts.db")
    >>> await manager.create_account(platform="twitter", username="user_001")
    >>> account = manager.get_account(platform="twitter", username="user_001")
    >>> manager.update_status(account.id, AccountStatus.ACTIVE)
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger


class AccountStatus(str, Enum):
    """Статус аккаунта."""
    CREATED = "created"
    WARMUP = "warmup"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    BANNED = "banned"
    DEAD = "dead"


class Platform(str, Enum):
    """Поддерживаемые платформы."""
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TELEGRAM = "telegram"
    VK = "vk"
    REDDIT = "reddit"
    DISCORD = "discord"
    GITHUB = "github"
    HABR = "habr"
    VC_RU = "vcru"
    YANDEX = "yandex"
    MAILRU = "mailru"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    CUSTOM = "custom"


@dataclass
class Account:
    """Аккаунт на платформе."""
    id: int = 0
    platform: str = ""
    username: str = ""
    email: str = ""
    password_encrypted: str = ""
    phone: str = ""
    status: str = AccountStatus.CREATED
    proxy_url: str = ""
    profile_id: str = ""
    session_name: str = ""
    created_at: float = 0
    last_used_at: float = 0
    last_action_at: float = 0
    total_actions: int = 0
    daily_actions: int = 0
    daily_limit: int = 100
    cooldown_until: float = 0
    ban_reason: str = ""
    metadata_json: str = "{}"
    tags: str = ""

    @property
    def metadata(self) -> dict[str, Any]:
        try:
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    @property
    def is_available(self) -> bool:
        if self.status in (AccountStatus.BANNED, AccountStatus.DEAD):
            return False
        if self.status == AccountStatus.COOLDOWN and time.time() < self.cooldown_until:
            return False
        if self.daily_actions >= self.daily_limit:
            return False
        return True

    @property
    def cooldown_remaining(self) -> float:
        if self.status != AccountStatus.COOLDOWN:
            return 0
        return max(0, self.cooldown_until - time.time())


class AccountManager:
    """Менеджер аккаунтов с SQLite хранилищем."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: str = "/tmp/accounts.db",
        encryption_key: str = "",
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._encryption_key = encryption_key
        self._fernet = self._init_fernet(encryption_key)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _init_fernet(self, key):
        """Инициализировать Fernet-шифрование."""
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            raise ImportError(
                "cryptography package required for encryption. "
                "Install: pip install cryptography>=42.0.0"
            )

        if key and len(key) > 0:
            try:
                return Fernet(key.encode() if isinstance(key, str) else key)
            except Exception:
                import hashlib
                import base64
                derived = hashlib.sha256(key.encode()).digest()
                fernet_key = base64.urlsafe_b64encode(derived)
                return Fernet(fernet_key)
        else:
            logger.warning(
                "No encryption key provided — generating ephemeral key. "
                "Passwords will be unrecoverable after restart. "
                "Set encryption_key or use AccountManager.generate_key()."
            )
            return Fernet(Fernet.generate_key())

    @staticmethod
    def generate_key() -> str:
        """Сгенерировать новый Fernet-ключ."""
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                email TEXT DEFAULT '',
                password_encrypted TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                status TEXT DEFAULT 'created',
                proxy_url TEXT DEFAULT '',
                profile_id TEXT DEFAULT '',
                session_name TEXT DEFAULT '',
                created_at REAL DEFAULT 0,
                last_used_at REAL DEFAULT 0,
                last_action_at REAL DEFAULT 0,
                total_actions INTEGER DEFAULT 0,
                daily_actions INTEGER DEFAULT 0,
                daily_limit INTEGER DEFAULT 100,
                cooldown_until REAL DEFAULT 0,
                ban_reason TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                tags TEXT DEFAULT '',
                UNIQUE(platform, username)
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT DEFAULT '',
                status TEXT DEFAULT 'success',
                error TEXT DEFAULT '',
                timestamp REAL DEFAULT 0,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );

            CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform);
            CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
            CREATE INDEX IF NOT EXISTS idx_action_log_account ON action_log(account_id);
            CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log(timestamp);
        """)
        self._conn.commit()

    def create_account(
        self,
        platform: str,
        username: str,
        email: str = "",
        password: str = "",
        phone: str = "",
        proxy_url: str = "",
        profile_id: str = "",
        daily_limit: int = 100,
        tags: str = "",
        metadata: dict | None = None,
    ) -> Account:
        password_enc = self._encrypt(password) if password else ""
        now = time.time()

        try:
            cursor = self._conn.execute(
                """INSERT INTO accounts
                   (platform, username, email, password_encrypted, phone, status,
                    proxy_url, profile_id, created_at, daily_limit, metadata_json, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    platform, username, email, password_enc, phone,
                    AccountStatus.CREATED, proxy_url, profile_id,
                    now, daily_limit,
                    json.dumps(metadata or {}), tags,
                ),
            )
            self._conn.commit()

            account = Account(
                id=cursor.lastrowid,
                platform=platform,
                username=username,
                email=email,
                password_encrypted=password_enc,
                phone=phone,
                status=AccountStatus.CREATED,
                proxy_url=proxy_url,
                profile_id=profile_id,
                created_at=now,
                daily_limit=daily_limit,
                metadata_json=json.dumps(metadata or {}),
                tags=tags,
            )

            logger.info(f"Account created: {platform}/{username} (id={account.id})")
            return account

        except sqlite3.IntegrityError:
            raise ValueError(f"Account already exists: {platform}/{username}")

    def get_account(self, account_id: int) -> Account | None:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return self._row_to_account(row) if row else None

    def get_account_by_username(
        self, platform: str, username: str
    ) -> Account | None:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE platform = ? AND username = ?",
            (platform, username),
        ).fetchone()
        return self._row_to_account(row) if row else None

    def get_accounts(
        self,
        platform: str | None = None,
        status: str | None = None,
        tags: str | None = None,
        limit: int = 100,
    ) -> list[Account]:
        query = "SELECT * FROM accounts WHERE 1=1"
        params: list[Any] = []

        if platform:
            query += " AND platform = ?"
            params.append(platform)

        if status:
            query += " AND status = ?"
            params.append(status)

        if tags:
            query += " AND tags LIKE ?"
            params.append(f"%{tags}%")

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_account(r) for r in rows]

    def get_available_accounts(self, platform: str) -> list[Account]:
        all_active = self.get_accounts(
            platform=platform,
            status=AccountStatus.ACTIVE,
        )
        return [a for a in all_active if a.is_available]

    def get_next_account(self, platform: str) -> Account | None:
        available = self.get_available_accounts(platform)
        if not available:
            return None
        available.sort(key=lambda a: a.daily_actions)
        return available[0]

    def update_status(
        self,
        account_id: int,
        status: str,
        reason: str = "",
    ) -> bool:
        account = self.get_account(account_id)
        if not account:
            return False

        updates = {"status": status}

        if status == AccountStatus.COOLDOWN:
            cooldown_hours = 1
            updates["cooldown_until"] = time.time() + cooldown_hours * 3600

        if status == AccountStatus.BANNED:
            updates["ban_reason"] = reason

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]

        self._conn.execute(
            f"UPDATE accounts SET {set_clause} WHERE id = ?",
            values,
        )
        self._conn.commit()

        logger.info(f"Account {account_id} status: {account.status} -> {status}")
        return True

    def record_action(
        self,
        account_id: int,
        action_type: str,
        target: str = "",
        status: str = "success",
        error: str = "",
        metadata: dict | None = None,
    ) -> None:
        now = time.time()

        self._conn.execute(
            """UPDATE accounts SET
               total_actions = total_actions + 1,
               daily_actions = daily_actions + 1,
               last_used_at = ?,
               last_action_at = ?
               WHERE id = ?""",
            (now, now, account_id),
        )

        self._conn.execute(
            """INSERT INTO action_log
               (account_id, action_type, target, status, error, timestamp, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, action_type, target, status, error, now, json.dumps(metadata or {})),
        )

        self._conn.commit()

    def reset_daily_counters(self) -> int:
        cursor = self._conn.execute(
            "UPDATE accounts SET daily_actions = 0 WHERE daily_actions > 0"
        )
        self._conn.commit()
        count = cursor.rowcount
        if count:
            logger.info(f"Reset daily counters for {count} accounts")
        return count

    def set_cooldown(
        self,
        account_id: int,
        hours: float = 1.0,
    ) -> None:
        cooldown_until = time.time() + hours * 3600
        self._conn.execute(
            "UPDATE accounts SET status = ?, cooldown_until = ? WHERE id = ?",
            (AccountStatus.COOLDOWN, cooldown_until, account_id),
        )
        self._conn.commit()
        logger.info(f"Account {account_id} on cooldown for {hours}h")

    def get_password(self, account: Account) -> str:
        return self._decrypt(account.password_encrypted)

    def get_stats(self, platform: str | None = None) -> dict[str, Any]:
        if platform:
            where = "WHERE platform = ?"
            params: list = [platform]
        else:
            where = ""
            params = []

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM accounts {where}", params
        ).fetchone()[0]

        by_status = {}
        for status in AccountStatus:
            if where:
                query = f"SELECT COUNT(*) FROM accounts {where} AND status = ?"
                query_params = params + [status.value]
            else:
                query = "SELECT COUNT(*) FROM accounts WHERE status = ?"
                query_params = [status.value]
            count = self._conn.execute(query, query_params).fetchone()[0]
            by_status[status.value] = count

        total_actions = self._conn.execute(
            f"SELECT COALESCE(SUM(total_actions), 0) FROM accounts {where}", params
        ).fetchone()[0]

        return {
            "total": total,
            "by_status": by_status,
            "total_actions": total_actions,
            "platform": platform or "all",
        }

    def get_action_history(
        self,
        account_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT * FROM action_log
               WHERE account_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (account_id, limit),
        ).fetchall()

        return [dict(r) for r in rows]

    def delete_account(self, account_id: int) -> bool:
        cursor = self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self._conn.commit()
        if cursor.rowcount:
            logger.info(f"Account {account_id} deleted")
            return True
        return False

    def close(self) -> None:
        self._conn.close()

    # ─── Внутренние методы ─────────────────────────────────────────────────

    def _row_to_account(self, row: sqlite3.Row) -> Account:
        d = dict(row)
        return Account(**{k: d[k] for k in d if k in Account.__dataclass_fields__})

    def _encrypt(self, plaintext: str) -> str:
        """Зашифровать строку через Fernet (AES-128-CBC + HMAC-SHA256)."""
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        """Расшифровать строку через Fernet."""
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ""
