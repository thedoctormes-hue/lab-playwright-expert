"""Экспорт OpenAPI спецификации из FastAPI приложения.

Использование:
    python scripts/export_openapi.py
    python scripts/export_openapi.py --output docs/openapi.json
    python scripts/export_openapi.py --format yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Добавить src в path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def export_openapi(output: str = "docs/openapi.json", fmt: str = "json") -> str:
    """Экспортировать OpenAPI спецификацию.

    Args:
        output: Путь к выходному файлу
        fmt: Формат (json или yaml)

    Returns:
        Путь к созданному файлу
    """
    from lab_playwright_kit.saas_api import create_app

    app = create_app()
    schema = app.openapi()

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "yaml":
        try:
            import yaml
            content = yaml.dump(schema, default_flow_style=False, allow_unicode=True)
            out_path = out_path.with_suffix(".yaml")
        except ImportError:
            print("PyYAML не установлен, используем JSON")
            content = json.dumps(schema, indent=2, ensure_ascii=False)
    else:
        content = json.dumps(schema, indent=2, ensure_ascii=False)

    out_path.write_text(content, encoding="utf-8")
    print(f"OpenAPI спецификация сохранена: {out_path}")
    endpoint_count = sum(1 for r in app.routes if hasattr(r, 'path') and r.path.startswith("/api/"))
    print(f"  Эндпоинтов: {endpoint_count}")
    print(f"  Размер: {len(content)} байт")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Экспорт OpenAPI спецификации")
    parser.add_argument("--output", default="docs/openapi.json", help="Выходной файл")
    parser.add_argument("--format", choices=["json", "yaml"], default="json", help="Формат")
    args = parser.parse_args()
    export_openapi(output=args.output, fmt=args.format)


if __name__ == "__main__":
    main()
