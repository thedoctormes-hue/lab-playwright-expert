"""
Общие фикстуры для тестов.
"""
import os
import sys
from pathlib import Path


# Добавить src и scripts в sys.path для импорта пакета
# pythonpath в pyproject.toml не работает для вложенных import в тестах
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (_PROJECT_ROOT / "src", _PROJECT_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def pytest_configure(config):
    """Установить переменные окружения для тестов."""
    # Токен для screenshot_service тестов
    os.environ.setdefault("SCREENSHOT_SERVICE_TOKEN", "test-token-for-pytest-12345678")
