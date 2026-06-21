"""Scrapy Pipelines — обработка, валидация и экспорт данных."""

from .dedup_pipeline import DedupPipeline
from .export_pipeline import ExportPipeline
from .validation_pipeline import ValidationPipeline


__all__ = [
    "ValidationPipeline",
    "ExportPipeline",
    "DedupPipeline",
]
