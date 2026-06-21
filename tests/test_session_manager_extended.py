"""
Расширенные тесты для SessionManager.

Покрывает:
  - SessionData (is_expired, age_seconds, to_dict, from_dict)
  - SessionManager.__init__
  - SessionManager._validate_name
  - SessionManager.session_exists (via disk)
  - SessionManager.list_sessions
  - SessionManager.get_session_info
  - SessionManager.cleanup_expired
  - SessionManager.delete_session
"""

from __future__ import annotations

import time

import pytest

from lab_playwright_kit.session_manager import SessionData, SessionManager


# ─── SessionData ───────────────────────────────────────────────────────────


class TestSessionData:
    def test_defaults(self):
        s = SessionData(name="test")
        assert s.name == "test"
        assert s.cookies == []
        assert s.local_storage == {}
        assert s.session_storage == {}
        assert s.url == ""
        assert s.ttl_seconds == 0
        assert s.metadata == {}

    def test_is_expired_no_ttl(self):
        s = SessionData(name="test", ttl_seconds=0)
        assert s.is_expired is False

    def test_is_expired_not_yet(self):
        s = SessionData(name="test", ttl_seconds=3600, updated_at=time.time())
        assert s.is_expired is False

    def test_is_expired_yes(self):
        s = SessionData(name="test", ttl_seconds=1, updated_at=time.time() - 10)
        assert s.is_expired is True

    def test_age_seconds(self):
        s = SessionData(name="test", updated_at=time.time() - 60)
        assert 59 <= s.age_seconds <= 61

    def test_to_dict(self):
        s = SessionData(
            name="test",
            cookies=[{"name": "a"}],
            local_storage={"k": "v"},
            url="https://example.com",
            ttl_seconds=3600,
        )
        d = s.to_dict()
        assert d["name"] == "test"
        assert d["cookies"] == [{"name": "a"}]
        assert d["local_storage"] == {"k": "v"}
        assert d["url"] == "https://example.com"
        assert d["ttl_seconds"] == 3600

    def test_from_dict(self):
        data = {
            "name": "test",
            "cookies": [{"name": "a"}],
            "local_storage": {"k": "v"},
            "session_storage": {},
            "url": "https://example.com",
            "created_at": 1000.0,
            "updated_at": 2000.0,
            "ttl_seconds": 3600,
            "metadata": {"key": "val"},
        }
        s = SessionData.from_dict(data)
        assert s.name == "test"
        assert s.cookies == [{"name": "a"}]
        assert s.local_storage == {"k": "v"}
        assert s.url == "https://example.com"
        assert s.created_at == 1000.0
        assert s.updated_at == 2000.0
        assert s.ttl_seconds == 3600
        assert s.metadata == {"key": "val"}

    def test_roundtrip(self):
        original = SessionData(
            name="roundtrip",
            cookies=[{"name": "c1"}],
            local_storage={"lk": "lv"},
            url="https://test.com",
            ttl_seconds=7200,
        )
        restored = SessionData.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.cookies == original.cookies
        assert restored.local_storage == original.local_storage
        assert restored.url == original.url
        assert restored.ttl_seconds == original.ttl_seconds


# ─── SessionManager ────────────────────────────────────────────────────────


class TestSessionManager:
    def test_init_creates_dir(self, tmp_path):
        d = tmp_path / "sessions"
        mgr = SessionManager(storage_dir=str(d))
        assert d.exists()
        assert mgr.storage_dir == d

    def test_init_with_key(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")
        assert mgr._fernet is not None

    def test_validate_name_empty(self):
        mgr = SessionManager(storage_dir="/tmp/test_sessions_1")
        with pytest.raises(ValueError, match="empty"):
            mgr._validate_name("")

    def test_validate_name_whitespace(self):
        mgr = SessionManager(storage_dir="/tmp/test_sessions_2")
        with pytest.raises(ValueError, match="empty"):
            mgr._validate_name("   ")

    def test_validate_name_forbidden_chars(self):
        mgr = SessionManager(storage_dir="/tmp/test_sessions_3")
        for ch in '/\\:*?"<>|':
            with pytest.raises(ValueError, match="forbidden"):
                mgr._validate_name(f"test{ch}name")

    def test_validate_name_ok(self):
        mgr = SessionManager(storage_dir="/tmp/test_sessions_4")
        mgr._validate_name("valid_session_name")

    def test_session_exists_not_found(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path))
        assert mgr.session_exists("nonexistent") is False

    def test_list_sessions_empty(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path))
        assert mgr.list_sessions() == []

    def test_get_session_info_not_found(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path))
        assert mgr.get_session_info("nonexistent") is None

    def test_delete_session_not_found(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path))
        assert mgr.delete_session("nonexistent") is False

    def test_save_and_exists(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")
        # Directly save to disk
        sd = SessionData(
            name="test_session",
            cookies=[{"name": "c1"}],
            url="https://example.com",
        )
        mgr._save_to_disk(sd)

        assert mgr.session_exists("test_session") is True

    def test_list_sessions_with_data(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")
        sd = SessionData(name="s1", url="https://a.com")
        mgr._save_to_disk(sd)

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "s1"
        assert sessions[0]["url"] == "https://a.com"

    def test_get_session_info(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")
        sd = SessionData(name="info_test", url="https://info.com", ttl_seconds=3600)
        mgr._save_to_disk(sd)

        info = mgr.get_session_info("info_test")
        assert info is not None
        assert info["name"] == "info_test"
        assert info["url"] == "https://info.com"

    def test_delete_session(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")
        sd = SessionData(name="to_delete")
        mgr._save_to_disk(sd)

        assert mgr.session_exists("to_delete") is True
        assert mgr.delete_session("to_delete") is True
        assert mgr.session_exists("to_delete") is False

    def test_cleanup_expired(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="test-key")

        # Save expired session
        sd_expired = SessionData(
            name="expired",
            ttl_seconds=1,
            updated_at=time.time() - 100,
        )
        mgr._save_to_disk(sd_expired)

        # Save fresh session
        sd_fresh = SessionData(
            name="fresh",
            ttl_seconds=3600,
            updated_at=time.time(),
        )
        mgr._save_to_disk(sd_fresh)

        removed = mgr.cleanup_expired()
        assert removed >= 1
        assert mgr.session_exists("expired") is False
        assert mgr.session_exists("fresh") is True

    def test_save_load_roundtrip(self, tmp_path):
        mgr = SessionManager(storage_dir=str(tmp_path), encryption_key="roundtrip-key")
        sd = SessionData(
            name="roundtrip",
            cookies=[{"name": "c1", "value": "v1"}],
            local_storage={"lk": "lv"},
            session_storage={"sk": "sv"},
            url="https://roundtrip.com",
            ttl_seconds=7200,
            metadata={"mkey": "mval"},
        )
        mgr._save_to_disk(sd)

        loaded = mgr._load_from_disk("roundtrip")
        assert loaded is not None
        assert loaded.name == "roundtrip"
        assert loaded.cookies == [{"name": "c1", "value": "v1"}]
        assert loaded.local_storage == {"lk": "lv"}
        assert loaded.session_storage == {"sk": "sv"}
        assert loaded.url == "https://roundtrip.com"
        assert loaded.ttl_seconds == 7200
        assert loaded.metadata == {"mkey": "mval"}
