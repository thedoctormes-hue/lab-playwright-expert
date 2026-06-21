"""ExportPipeline — экспорт Scrapy items в JSON, CSV, SQLite."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scrapy.exceptions import NotConfigured


log = logging.getLogger(__name__)


class ExportPipeline:
    """
    Экспорт items в файлы.

    Поддерживаемые форматы: json, csv, sqlite

    Конфигурация через Scrapy settings:
        EXPORT_FORMAT = "json"           # json | csv | sqlite
        EXPORT_DIR = "./crawl_output"    # директория для файлов
        EXPORT_BATCH_SIZE = 100          # размер батча для flush
    """

    def __init__(self, fmt: str, output_dir: str, batch_size: int):
        self._fmt = fmt
        self._output_dir = Path(output_dir)
        self._batch_size = batch_size
        self._buffer: list[dict] = []
        self._file_index = 0

    @classmethod
    def from_crawler(cls, crawler):
        fmt = crawler.settings.get("EXPORT_FORMAT", "json")
        output_dir = crawler.settings.get("EXPORT_DIR", "./crawl_output")
        batch_size = crawler.settings.getint("EXPORT_BATCH_SIZE", 100)

        if fmt not in ("json", "csv", "sqlite"):
            raise NotConfigured(f"Unknown export format: {fmt}")

        return cls(fmt=fmt, output_dir=output_dir, batch_size=batch_size)

    def open_spider(self, spider):
        """Создать выходную директорию и файлы."""
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            if self._fmt == "sqlite":
                spider_name = spider.name if spider else "crawl"
                db_path = self._output_dir / f"{spider_name}.db"
                self._sqlite_conn = sqlite3.connect(str(db_path))
                self._sqlite_conn.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_type TEXT,
                        data TEXT,
                        crawl_time TEXT
                    )
                """)
                self._sqlite_conn.commit()
        except Exception as e:
            log.error("Export open_spider error: %s", e)

    def close_spider(self, spider):
        """Финализировать экспорт."""
        try:
            if self._buffer:
                self._flush(spider)
            if self._fmt == "sqlite" and hasattr(self, "_sqlite_conn"):
                self._sqlite_conn.close()
        except Exception as e:
            log.error("Export close_spider error: %s", e)

    def process_item(self, item, spider):
        """Добавить item в буфер."""
        try:
            data = dict(item)
            data["_item_type"] = type(item).__name__
            data["_crawl_time"] = datetime.now(timezone.utc).isoformat()
            self._buffer.append(data)
            if len(self._buffer) >= self._batch_size:
                self._flush(spider)
            return item
        except Exception as e:
            log.error("Export process_item error: %s", e)
            return item

    def _flush(self, spider):
        """Записать буфер в файл."""
        if not self._buffer:
            return
        try:
            if self._fmt == "json":
                self._flush_json(spider)
            elif self._fmt == "csv":
                self._flush_csv(spider)
            elif self._fmt == "sqlite":
                self._flush_sqlite()
            self._buffer.clear()
        except Exception as e:
            log.error("Export flush error: %s", e)

    def _flush_json(self, spider):
        spider_name = spider.name if spider else "crawl"
        filepath = self._output_dir / f"{spider_name}_{self._file_index}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._buffer, f, ensure_ascii=False, indent=2)
            self._file_index += 1
            log.info("Exported %d items to %s", len(self._buffer), filepath)
        except OSError as e:
            log.error("Failed to write JSON: %s", e)

    def _flush_csv(self, spider):
        spider_name = spider.name if spider else "crawl"
        filepath = self._output_dir / f"{spider_name}.csv"
        try:
            file_exists = filepath.exists()
            all_keys = []
            for item in self._buffer:
                for k in item:
                    if k not in all_keys:
                        all_keys.append(k)
            with open(filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                writer.writerows(self._buffer)
        except OSError as e:
            log.error("Failed to write CSV: %s", e)

    def _flush_sqlite(self):
        try:
            self._sqlite_conn.executemany(
                "INSERT INTO items (item_type, data, crawl_time) VALUES (?, ?, ?)",
                [
                    (
                        d.get("_item_type", ""),
                        json.dumps(d, ensure_ascii=False),
                        d.get("_crawl_time", ""),
                    )
                    for d in self._buffer
                ],
            )
            self._sqlite_conn.commit()
        except sqlite3.Error as e:
            log.error("SQLite error: %s", e)
