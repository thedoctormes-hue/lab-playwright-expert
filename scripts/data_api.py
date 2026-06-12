"""
Data API — FastAPI сервис для доступа к спарсенным данным.

REST API для:
- Запуска парсинга по URL (sync/async)
- Получения результатов из PostgreSQL
- Поиска и фильтрации данных
- Экспорта в CSV/JSON
- Управления задачами парсинга

API Endpoints:
  POST /api/v1/parse              — Запустить парсинг URL
  POST /api/v1/parse/batch        — Пакетный парсинг
  GET  /api/v1/results            — Список результатов (с фильтрами)
  GET  /api/v1/results/{id}       — Получить результат по ID
  GET  /api/v1/results/search     — Поиск по данным
  DELETE /api/v1/results/{id}     — Удалить результат
  GET  /api/v1/export/csv         — Экспорт в CSV
  GET  /api/v1/export/json        — Экспорт в JSON
  GET  /api/v1/stats              — Статистика
  GET  /api/v1/schemas            — Список доступных схем
  GET  /api/v1/health             — Health check

Запуск:
  export DATABASE_URL="postgresql://user:pass@localhost:5432/parser_db"
  export DATA_API_TOKEN="your-secret-token"
  PYTHONPATH=src uvicorn scripts.data_api:app --host 0.0.0.0 --port 8180
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

# ─── Setup path ──────────────────────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lab_playwright_kit import (
    NicheType,
    NicheSchema,
    FieldMapping,
    get_schema,
    detect_niche,
    SCHEMA_REGISTRY,
    BrowserManager,
    DataParser,
)


# ─── Config ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATA_API_DATABASE_URL", "sqlite:///./data_api.db")
API_TOKEN = os.environ.get("DATA_API_TOKEN", "")
MAX_BATCH_SIZE = int(os.environ.get("DATA_API_MAX_BATCH_SIZE", "50"))
DEFAULT_PAGE_SIZE = int(os.environ.get("DATA_API_DEFAULT_PAGE_SIZE", "20"))
MAX_PAGE_SIZE = int(os.environ.get("DATA_API_MAX_PAGE_SIZE", "100"))


# ─── Database layer ──────────────────────────────────────────────────────────

class Database:
    """Абстрактный слой БД — SQLite (по умолчанию) или PostgreSQL."""

    def __init__(self, url: str):
        self.url = url
        self._conn = None
        self._is_postgres = url.startswith("postgresql://")

    def connect(self):
        """Подключиться к БД."""
        if self._is_postgres:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self.url)
                logger.info("Connected to PostgreSQL")
            except ImportError:
                logger.warning("psycopg2 not installed, falling back to SQLite")
                self._is_postgres = False
                self.url = "sqlite:///./data_api.db"
                self._connect_sqlite()
        else:
            self._connect_sqlite()

    def _connect_sqlite(self):
        import sqlite3
        db_path = self.url.replace("sqlite:///", "")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        logger.info(f"Connected to SQLite: {db_path}")

    def init_schema(self):
        """Создать таблицы."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS parse_results (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                niche TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT,
                data TEXT,
                confidence REAL DEFAULT 0.0,
                parse_time_ms REAL DEFAULT 0.0,
                content_hash TEXT,
                errors TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS parse_tasks (
                id TEXT PRIMARY KEY,
                urls TEXT NOT NULL,
                niche TEXT,
                status TEXT DEFAULT 'pending',
                total_urls INTEGER DEFAULT 0,
                completed_urls INTEGER DEFAULT 0,
                failed_urls INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_results_niche ON parse_results(niche)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_results_domain ON parse_results(domain)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_results_created ON parse_results(created_at)
        """)
        self._conn.commit()

    def insert_result(self, result: dict[str, Any]) -> str:
        """Сохранить результат парсинга."""
        result_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO parse_results
            (id, url, niche, domain, title, data, confidence,
             parse_time_ms, content_hash, errors, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                result.get("url", ""),
                result.get("niche", ""),
                result.get("domain", ""),
                result.get("page_title", ""),
                json.dumps(result.get("data", {}), ensure_ascii=False),
                result.get("confidence", 0.0),
                result.get("parse_time_ms", 0.0),
                result.get("content_hash", ""),
                json.dumps(result.get("errors", []), ensure_ascii=False),
                now,
                now,
            ),
        )
        self._conn.commit()
        return result_id

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        """Получить результат по ID."""
        row = self._conn.execute(
            "SELECT * FROM parse_results WHERE id = ?", (result_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_results(
        self,
        niche: str | None = None,
        domain: str | None = None,
        min_confidence: float = 0.0,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Список результатов с фильтрами и пагинацией."""
        conditions = ["1=1"]
        params: list[Any] = []

        if niche:
            conditions.append("niche = ?")
            params.append(niche)
        if domain:
            conditions.append("domain LIKE ?")
            params.append(f"%{domain}%")
        if min_confidence > 0:
            conditions.append("confidence >= ?")
            params.append(min_confidence)
        if search:
            conditions.append("(title LIKE ? OR data LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions)

        # Count
        count_row = self._conn.execute(
            f"SELECT COUNT(*) FROM parse_results WHERE {where}", params
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Results
        offset = (page - 1) * page_size
        rows = self._conn.execute(
            f"""
            SELECT * FROM parse_results
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        return [self._row_to_dict(row) for row in rows], total

    def delete_result(self, result_id: str) -> bool:
        """Удалить результат."""
        cursor = self._conn.execute(
            "DELETE FROM parse_results WHERE id = ?", (result_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_stats(self) -> dict[str, Any]:
        """Статистика."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM parse_results"
        ).fetchone()[0]

        by_niche = {}
        for row in self._conn.execute(
            "SELECT niche, COUNT(*) FROM parse_results GROUP BY niche"
        ).fetchall():
            by_niche[row[0]] = row[1]

        by_domain = {}
        for row in self._conn.execute(
            "SELECT domain, COUNT(*) FROM parse_results GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall():
            by_domain[row[0]] = row[1]

        avg_confidence = self._conn.execute(
            "SELECT AVG(confidence) FROM parse_results"
        ).fetchone()[0]

        avg_parse_time = self._conn.execute(
            "SELECT AVG(parse_time_ms) FROM parse_results"
        ).fetchone()[0]

        return {
            "total_results": total,
            "by_niche": by_niche,
            "by_domain": by_domain,
            "avg_confidence": round(avg_confidence or 0, 3),
            "avg_parse_time_ms": round(avg_parse_time or 0, 1),
        }

    def _row_to_dict(self, row) -> dict[str, Any]:
        """Конвертировать row в dict."""
        d = dict(row)
        # Распарсить JSON поля
        for field in ("data", "errors"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def close(self):
        if self._conn:
            self._conn.close()


# ─── Pydantic models ─────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    url: str
    niche: str | None = None
    custom_schema: dict[str, Any] | None = None
    priority: int = Field(default=5, ge=1, le=10)


class BatchParseRequest(BaseModel):
    urls: list[str] = Field(..., max_length=50)
    niche: str | None = None
    max_concurrent: int = Field(default=3, ge=1, le=10)


class ParseResponse(BaseModel):
    id: str
    url: str
    niche: str
    domain: str
    title: str | None = None
    data: dict[str, Any]
    confidence: float
    parse_time_ms: float
    errors: list[str]
    created_at: str


class BatchParseResponse(BaseModel):
    task_id: str
    total_urls: int
    status: str
    results: list[ParseResponse]


class StatsResponse(BaseModel):
    total_results: int
    by_niche: dict[str, int]
    by_domain: dict[str, int]
    avg_confidence: float
    avg_parse_time_ms: float


class SchemaInfo(BaseModel):
    niche: str
    name: str
    description: str
    fields: list[str]
    url_patterns: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    uptime_seconds: float


# ─── App setup ───────────────────────────────────────────────────────────────

db = Database(DATABASE_URL)
_start_time = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    db.init_schema()
    logger.info("Data API started")
    yield
    db.close()
    logger.info("Data API stopped")


app = FastAPI(
    title="Data Parser API",
    description="REST API для доступа к спарсенным данным",
    version="2.0.0",
    lifespan=lifespan,
)


# ─── Auth dependency ─────────────────────────────────────────────────────────

async def verify_token(request: Request):
    """Проверка Bearer token (опциональная если DATA_API_TOKEN не задан)."""
    if not API_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth[7:]
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return True


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check."""
    return HealthResponse(
        status="ok",
        version="2.0.0",
        database="postgresql" if db._is_postgres else "sqlite",
        uptime_seconds=round(time.monotonic() - _start_time, 1),
    )


@app.get("/api/v1/schemas")
async def list_schemas(_=Depends(verify_token)):
    """Список доступных схем парсинга."""
    schemas = []
    for niche_type, schema in SCHEMA_REGISTRY.items():
        schemas.append(SchemaInfo(
            niche=niche_type.value,
            name=schema.name,
            description=schema.description,
            fields=schema.get_field_names(),
            url_patterns=schema.url_patterns,
        ))
    return {"schemas": schemas, "total": len(schemas)}


@app.post("/api/v1/parse", response_model=ParseResponse)
async def parse_url(request: ParseRequest, _=Depends(verify_token)):
    """Запустить парсинг URL (sync — ждёт результат)."""
    from lab_playwright_kit import BrowserManager, DataParser

    niche_type = None
    if request.niche:
        try:
            niche_type = NicheType(request.niche)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown niche: {request.niche}")

    custom_schema = None
    if request.custom_schema:
        try:
            fields = [
                FieldMapping(**f) for f in request.custom_schema.get("fields", [])
            ]
            custom_schema = NicheSchema(
                niche=NicheType.CUSTOM,
                name=request.custom_schema.get("name", "Custom"),
                fields=fields,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid custom schema: {e}")

    try:
        bm = BrowserManager()
        await bm.launch()
        parser = DataParser(bm, niche=niche_type, custom_schema=custom_schema)
        result = await parser.parse(request.url)
        await parser.close()
        await bm.close()

        # Сохранить в БД
        result_dict = result.to_dict()
        result_dict["page_title"] = result.page_title
        result_id = db.insert_result(result_dict)

        return ParseResponse(
            id=result_id,
            url=result.url,
            niche=result.niche.value,
            domain=result.domain,
            title=result.page_title,
            data=result.data,
            confidence=result.confidence,
            parse_time_ms=result.parse_time_ms,
            errors=result.errors,
            created_at=result.parsed_at,
        )
    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/parse/batch")
async def parse_batch(request: BatchParseRequest, _=Depends(verify_token)):
    """Пакетный парсинг URL (async — возвращает task_id)."""
    if len(request.urls) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Too many URLs. Max: {MAX_BATCH_SIZE}",
        )

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db._conn.execute(
        """
        INSERT INTO parse_tasks (id, urls, niche, status, total_urls, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            json.dumps(request.urls),
            request.niche or "",
            "pending",
            len(request.urls),
            now,
            now,
        ),
    )
    db._conn.commit()

    # TODO: Запустить фоновую задачу парсинга
    # Пока возвращаем task_id — реальный парсинг через Celery/RQ

    return {
        "task_id": task_id,
        "total_urls": len(request.urls),
        "status": "pending",
        "message": "Task created. Poll /api/v1/tasks/{task_id} for status.",
    }


@app.get("/api/v1/results")
async def list_results(
    niche: str | None = None,
    domain: str | None = None,
    min_confidence: float = 0.0,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _=Depends(verify_token),
):
    """Список результатов с фильтрами и пагинацией."""
    results, total = db.list_results(
        niche=niche,
        domain=domain,
        min_confidence=min_confidence,
        search=search,
        page=page,
        page_size=page_size,
    )
    return {
        "results": results,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@app.get("/api/v1/results/{result_id}")
async def get_result(result_id: str, _=Depends(verify_token)):
    """Получить результат по ID."""
    result = db.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@app.delete("/api/v1/results/{result_id}")
async def delete_result(result_id: str, _=Depends(verify_token)):
    """Удалить результат."""
    if db.delete_result(result_id):
        return {"status": "deleted", "id": result_id}
    raise HTTPException(status_code=404, detail="Result not found")


@app.get("/api/v1/export/csv")
async def export_csv(
    niche: str | None = None,
    domain: str | None = None,
    min_confidence: float = 0.0,
    _=Depends(verify_token),
):
    """Экспорт результатов в CSV."""
    results, total = db.list_results(
        niche=niche,
        domain=domain,
        min_confidence=min_confidence,
        page=1,
        page_size=10000,
    )

    if not results:
        raise HTTPException(status_code=404, detail="No results to export")

    # Собрать все поля
    all_fields: list[str] = []
    field_set: set[str] = set()
    for r in results:
        data = r.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        for k in data.keys():
            if k not in field_set:
                all_fields.append(k)
                field_set.add(k)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "url", "niche", "domain", "confidence", "created_at"] + all_fields)

    for r in results:
        data = r.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        row = [
            r.get("id", ""),
            r.get("url", ""),
            r.get("niche", ""),
            r.get("domain", ""),
            r.get("confidence", 0),
            r.get("created_at", ""),
        ]
        for field in all_fields:
            val = data.get(field, "")
            if isinstance(val, list):
                val = "; ".join(str(v) for v in val)
            row.append(str(val) if val is not None else "")
        writer.writerow(row)

    csv_content = output.getvalue()
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export.csv"},
    )


@app.get("/api/v1/export/json")
async def export_json(
    niche: str | None = None,
    domain: str | None = None,
    min_confidence: float = 0.0,
    _=Depends(verify_token),
):
    """Экспорт результатов в JSON."""
    results, total = db.list_results(
        niche=niche,
        domain=domain,
        min_confidence=min_confidence,
        page=1,
        page_size=10000,
    )

    if not results:
        raise HTTPException(status_code=404, detail="No results to export")

    export_data = {
        "meta": {
            "total": total,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
    }

    return export_data


@app.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats(_=Depends(verify_token)):
    """Статистика по данным."""
    return StatsResponse(**db.get_stats())


# ─── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DATA_API_PORT", "8180"))
    host = os.environ.get("DATA_API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
