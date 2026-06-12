"""
Secret Manager — безопасное хранение и управление секретами.

Решает проблемы:
  1. Cookies хранятся в открытом виде (crosspost.py)
  2. API keys в коде (llm_parse.py)
  3. Нет ротации секретов

Использует:
  - Fernet шифрование (AES-128-CBC + HMAC-SHA256)
  - Файл ключей с правами 0600
  - Поддержка master key из env

Использование:
  from secret_manager import SecretManager

  sm = SecretManager()

  # Сохранить секрет
  sm.set("habr_cookies", json.dumps(cookies))

  # Получить секрет
  cookies = json.loads(sm.get("habr_cookies"))

  # Ротация мастер-ключа
  sm.rotate_master_key()
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import sys
from pathlib import Path

from loguru import logger


# ─── Конфигурация ───────────────────────────────────────────────

SECRETS_DIR = Path(os.getenv("SECRETS_DIR", "/root/LabDoctorM/.secrets"))
MASTER_KEY_FILE = SECRETS_DIR / ".master_key"
SECRETS_FILE = SECRETS_DIR / "vault.enc"


# ─── Криптография ────────────────────────────────────────────────

try:
    import base64

    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    logger.warning(
        "cryptography package not installed. "
        "Install: pip install cryptography"
    )


def _derive_key(master_key: str, salt: bytes) -> bytes:
    """Вывести Fernet-ключ из master key через PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,  # OWASP рекомендация для PBKDF2-SHA256
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
    return key


def _get_or_create_master_key() -> str:
    """Получить или создать master key."""
    # Приоритет: env → файл → генерация
    env_key = os.getenv("SECRETS_MASTER_KEY", "")
    if env_key:
        if len(env_key) < 16:
            logger.warning("SECRETS_MASTER_KEY слишком короткий (мин. 16 символов)")
        return env_key

    if MASTER_KEY_FILE.exists():
        key = MASTER_KEY_FILE.read_text().strip()
        # Проверить права файла
        file_stat = MASTER_KEY_FILE.stat()
        if file_stat.st_mode & (stat.S_IRGRP | stat.S_IROTH):
            logger.error(
                f"Master key file has insecure permissions: {oct(file_stat.st_mode)}. "
                f"Run: chmod 600 {MASTER_KEY_FILE}"
            )
            raise PermissionError(f"Insecure key file permissions: {MASTER_KEY_FILE}")
        return key

    # Генерация нового ключа
    new_key = secrets.token_urlsafe(32)
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    MASTER_KEY_FILE.write_text(new_key)
    MASTER_KEY_FILE.chmod(0o600)
    logger.warning(
        f"Generated new master key: {MASTER_KEY_FILE}. "
        f"BACKUP THIS FILE. Set SECRETS_MASTER_KEY env for production."
    )
    return new_key


# ─── Secret Manager ──────────────────────────────────────────────

class SecretManager:
    """Менеджер секретов с шифрованным хранилищем."""

    def __init__(
        self,
        secrets_dir: Path | None = None,
        master_key: str | None = None,
    ):
        if not _HAS_CRYPTO:
            raise RuntimeError(
                "cryptography package required. Install: pip install cryptography"
            )

        self._dir = secrets_dir or SECRETS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

        self._master_key = master_key or _get_or_create_master_key()
        self._salt_file = self._dir / ".salt"
        self._vault_file = self._dir / "vault.enc"

        # Получить или создать salt
        if self._salt_file.exists():
            self._salt = self._salt_file.read_bytes()
        else:
            self._salt = os.urandom(16)
            self._salt_file.write_bytes(self._salt)
            self._salt_file.chmod(0o600)

        self._fernet = Fernet(_derive_key(self._master_key, self._salt))
        self._cache: dict[str, str] = {}

    def _load_vault(self) -> dict[str, str]:
        """Загрузить и расшифровать хранилище."""
        if not self._vault_file.exists():
            return {}
        try:
            encrypted = self._vault_file.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted)
        except InvalidToken:
            logger.error("Failed to decrypt vault — wrong master key or corrupted data")
            raise ValueError("Cannot decrypt vault. Check SECRETS_MASTER_KEY.")
        except Exception as e:
            logger.error(f"Vault load error: {e}")
            return {}

    def _save_vault(self, data: dict[str, str]) -> None:
        """Зашифровать и сохранить хранилище."""
        plaintext = json.dumps(data).encode()
        encrypted = self._fernet.encrypt(plaintext)
        self._vault_file.write_bytes(encrypted)
        self._vault_file.chmod(0o600)

    def set(self, key: str, value: str) -> None:
        """Сохранить секрет."""
        vault = self._load_vault()
        vault[key] = value
        self._save_vault(vault)
        self._cache[key] = value
        logger.info(f"Secret set: {key}")

    def get(self, key: str) -> str | None:
        """Получить секрет."""
        if key in self._cache:
            return self._cache[key]
        vault = self._load_vault()
        value = vault.get(key)
        if value is not None:
            self._cache[key] = value
        return value

    def delete(self, key: str) -> bool:
        """Удалить секрет."""
        vault = self._load_vault()
        if key in vault:
            del vault[key]
            self._save_vault(vault)
            self._cache.pop(key, None)
            logger.info(f"Secret deleted: {key}")
            return True
        return False

    def list_keys(self) -> list[str]:
        """Список ключей (без значений)."""
        vault = self._load_vault()
        return list(vault.keys())

    def rotate_master_key(self, new_key: str | None = None) -> str:
        """Ротация master key — перешифровать все данные."""
        # Загрузить текущие данные
        vault = self._load_vault()

        # Новый ключ
        new_master = new_key or secrets.token_urlsafe(32)
        new_salt = os.urandom(16)
        new_fernet = Fernet(_derive_key(new_master, new_salt))

        # Перешифровать
        plaintext = json.dumps(vault).encode()
        encrypted = new_fernet.encrypt(plaintext)

        # Атомарная замена
        old_vault = self._vault_file.with_suffix(".enc.bak")
        old_salt = self._salt_file.with_suffix(".salt.bak")

        if self._vault_file.exists():
            self._vault_file.rename(old_vault)
        if self._salt_file.exists():
            self._salt_file.rename(old_salt)

        try:
            self._vault_file.write_bytes(encrypted)
            self._vault_file.chmod(0o600)
            self._salt_file.write_bytes(new_salt)
            self._salt_file.chmod(0o600)

            self._master_key = new_master
            self._salt = new_salt
            self._fernet = new_fernet

            # Удалить бэкапы
            old_vault.unlink(missing_ok=True)
            old_salt.unlink(missing_ok=True)

            logger.info("Master key rotated successfully")
            return new_master

        except Exception:
            # Откат
            if old_vault.exists():
                old_vault.rename(self._vault_file)
            if old_salt.exists():
                old_salt.rename(self._salt_file)
            raise

    def store_cookies(self, platform: str, cookies: list[dict]) -> None:
        """Сохранить cookies платформы в зашифрованном виде."""
        self.set(f"cookies_{platform}", json.dumps(cookies))
        logger.info(f"Cookies stored for {platform} ({len(cookies)} items)")

    def load_cookies(self, platform: str) -> list[dict] | None:
        """Загрузить cookies платформы."""
        raw = self.get(f"cookies_{platform}")
        if raw:
            return json.loads(raw)
        return None

    def store_api_key(self, service: str, api_key: str) -> None:
        """Сохранить API key."""
        self.set(f"apikey_{service}", api_key)
        logger.info(f"API key stored for {service}")

    def load_api_key(self, service: str) -> str | None:
        """Загрузить API key."""
        return self.get(f"apikey_{service}")


# ─── Утилита миграции ─────────────────────────────────────────────

def migrate_cookies_to_vault(
    cookies_file: str,
    platform: str,
    sm: SecretManager | None = None,
) -> bool:
    """
    Мигрировать cookies из открытого JSON в зашифрованное хранилище.
    После миграции удаляет исходный файл.
    """
    sm = sm or SecretManager()
    src = Path(cookies_file)

    if not src.exists():
        logger.warning(f"Cookie file not found: {src}")
        return False

    try:
        cookies = json.loads(src.read_text())
        sm.store_cookies(platform, cookies)

        # Безопасное удаление исходного файла
        # Перезаписать нулями перед удалением
        size = src.stat().st_size
        src.write_bytes(b"\x00" * size)
        src.unlink()

        logger.info(f"Migrated and deleted: {src}")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


# ─── CLI ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Secret Manager CLI")
    sub = parser.add_subparsers(dest="command")

    # set
    p_set = sub.add_parser("set", help="Сохранить секрет")
    p_set.add_argument("key")
    p_set.add_argument("value")

    # get
    p_get = sub.add_parser("get", help="Получить секрет")
    p_get.add_argument("key")

    # delete
    p_del = sub.add_parser("delete", help="Удалить секрет")
    p_del.add_argument("key")

    # list
    sub.add_parser("list", help="Список ключей")

    # rotate
    sub.add_parser("rotate", help="Ротация master key")

    # migrate-cookies
    p_mig = sub.add_parser("migrate-cookies", help="Мигрировать cookies в vault")
    p_mig.add_argument("platform")
    p_mig.add_argument("file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    sm = SecretManager()

    if args.command == "set":
        sm.set(args.key, args.value)
        print(f"Secret '{args.key}' saved.")

    elif args.command == "get":
        value = sm.get(args.key)
        if value:
            print(value)
        else:
            print(f"Secret '{args.key}' not found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "delete":
        if sm.delete(args.key):
            print(f"Secret '{args.key}' deleted.")
        else:
            print(f"Secret '{args.key}' not found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        keys = sm.list_keys()
        if keys:
            for k in keys:
                print(f"  {k}")
        else:
            print("  (empty vault)")

    elif args.command == "rotate":
        new_key = sm.rotate_master_key()
        print(f"Master key rotated. New key: {new_key}")
        print("IMPORTANT: Update SECRETS_MASTER_KEY env variable!")

    elif args.command == "migrate-cookies":
        if migrate_cookies_to_vault(args.file, args.platform, sm):
            print(f"Cookies migrated for {args.platform}")
        else:
            print("Migration failed.", file=sys.stderr)
            sys.exit(1)
