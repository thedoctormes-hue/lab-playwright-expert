"""
Price Parser — парсер прайс-листов медицинских лабораторий.

Поддерживаемые лаборатории:
  - Invitro (invitro.ru) — через API /golk/tests/api/v1/tests (2908 анализов)
  - CMD (cmd-online.ru) — через браузер + DOM (JS-рендеринг, ~30 на странице)
  - KDL (kdl.ru) — заглушка (403, требуется прокси/обход)

Использование:
    >>> from lab_playwright_kit.price_parser import PriceParser
    >>> parser = PriceParser()
    >>> prices = await parser.parse_all()
    >>> for lab, items in prices.items():
    ...     print(f"{lab}: {len(items)} анализов")
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from .browser import BrowserManager


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class PriceItem:
    """Один анализ из прайс-листа."""
    lab: str = ""
    code: str = ""
    name: str = ""
    price: int = 0
    currency: str = "RUB"
    duration: str = ""
    category: str = ""
    url: str = ""
    product_id: str = ""
    product_type: str = ""  # TEST, COMPLEX

    def to_dict(self) -> dict[str, Any]:
        return {
            "lab": self.lab,
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "currency": self.currency,
            "duration": self.duration,
            "category": self.category,
            "url": self.url,
            "product_id": self.product_id,
            "product_type": self.product_type,
        }


@dataclass
class PriceReport:
    """Отчёт о парсинге прайс-листа."""
    lab: str = ""
    items: list[PriceItem] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)
    total_price: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def avg_price(self) -> float:
        return self.total_price / len(self.items) if self.items else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lab": self.lab,
            "total_items": len(self.items),
            "categories": self.categories,
            "avg_price": round(self.avg_price, 2),
            "elapsed_seconds": self.elapsed_seconds,
            "errors": self.errors,
            "items": [i.to_dict() for i in self.items],
        }


# ─── Invitro Parser ──────────────────────────────────────────────────────────

class InvitroParser:
    """Парсер прайс-листа Invitro (invitro.ru).

    Использует внутренний API:
      /golk/tests/api/v1/tests?cityID=<id>&offset=<n>
      /golk/tests/api/v1/popular?cityID=<id>

    API возвращает JSON с пагинацией (limit=20, total≈2908).
    Структура: { total, limit, offset, data: [{ category_name, products: [...] }] }

    Каждый продукт содержит:
      bitrix_id, title, price, code, deadline, product_type, product_id
    """

    BASE_URL = "https://www.invitro.ru"
    CITY_ID_MOSCOW = "f1c3c4f0-3426-4cda-8449-e5d326e02f97"
    API_TESTS = f"{BASE_URL}/golk/tests/api/v1/tests"
    API_POPULAR = f"{BASE_URL}/golk/tests/api/v1/popular"

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout

    async def parse(self) -> PriceReport:
        """Парсить полный прайс-лист Invitro через API."""
        start = time.time()
        report = PriceReport(lab="Invitro")

        try:
            items = await self._fetch_all_tests()
            report.items = items

            categories: dict[str, int] = {}
            total = 0
            for item in report.items:
                cat = item.category or "Без категории"
                categories[cat] = categories.get(cat, 0) + 1
                total += item.price

            report.categories = categories
            report.total_price = total

        except Exception as e:
            report.errors.append(str(e))
            logger.error(f"Invitro parse error: {e}")

        report.elapsed_seconds = time.time() - start
        logger.info(f"Invitro: {len(report.items)} items, {report.elapsed_seconds:.1f}s")
        return report

    async def _fetch_all_tests(self) -> list[PriceItem]:
        """Получить все анализы через пагинированный API."""
        items = []
        city_id = self.CITY_ID_MOSCOW

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{self.BASE_URL}/analizy-i-tseny/",
                "Accept": "application/json",
            },
        ) as client:
            # Первый запрос — получаем total и limit
            first_page = await self._fetch_page(client, city_id, 0)
            if not first_page:
                return items

            total = first_page.get("total", 0)
            limit = first_page.get("limit", 20)
            data = first_page.get("data", [])

            logger.info(f"Invitro: total={total}, limit={limit}")

            # Обрабатываем первую страницу
            items.extend(self._extract_from_data(data))

            # Пагинация
            offsets = list(range(limit, total, limit))

            # Параллельно загружаем страницы (по 5 за раз)
            semaphore = asyncio.Semaphore(5)

            async def fetch_with_offset(offset: int) -> list[PriceItem]:
                async with semaphore:
                    page_data = await self._fetch_page(client, city_id, offset)
                    if page_data:
                        return self._extract_from_data(page_data.get("data", []))
                    return []

            tasks = [fetch_with_offset(off) for off in offsets]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    items.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Invitro page error: {result}")

        return items

    async def _fetch_page(
        self, client: httpx.AsyncClient, city_id: str, offset: int
    ) -> dict | None:
        """Получить одну страницу API."""
        url = f"{self.API_TESTS}?cityID={city_id}&offset={offset}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Invitro API: status={resp.status_code} at offset={offset}")
                return None
        except Exception as e:
            logger.warning(f"Invitro API error at offset={offset}: {e}")
            return None

    def _extract_from_data(self, data: list[dict]) -> list[PriceItem]:
        """Извлечь PriceItem из списка категорий."""
        items = []
        for category in data:
            cat_name = category.get("category_name", "")
            for product in category.get("products", []):
                try:
                    price = product.get("price", 0)
                    if price and int(price) > 0:
                        items.append(PriceItem(
                            lab="Invitro",
                            code=str(product.get("code", "")),
                            name=product.get("title", "").strip(),
                            price=int(price),
                            duration=f"{product.get('deadline', '')} к.д." if product.get('deadline') else "",
                            category=cat_name,
                            url=f"{self.BASE_URL}/analizy-i-tseny/{product.get('title', '').lower().replace(' ', '-')}_{product.get('bitrix_id', '')}/",
                            product_id=str(product.get("id", "")),
                            product_type=product.get("product_type", ""),
                        ))
                except (ValueError, TypeError):
                    continue
        return items


# ─── CMD Parser ──────────────────────────────────────────────────────────────

class CMDParser:
    """Парсер прайс-листа CMD (cmd-online.ru).

    CMD рендерит каталог через JavaScript.
    Структура DOM:
      section.analyze-section > article.analyze-item
        .analyze-item__title a — название + href
        .analyze-item__price — цена текстом "530 р."
        h2.analyze-section__title — категория

    Главная страница показывает ~30 анализов (ТОП).
    Полный каталог требует навигации по категориям.
    """

    BASE_URL = "https://www.cmd-online.ru"
    CATALOG_URL = f"{BASE_URL}/analizy-i-tseny/katalog-analizov/msk/"

    def __init__(self, browser_manager: BrowserManager | None = None, timeout: float = 60.0):
        self.timeout = timeout
        self._bm = browser_manager

    async def parse(self) -> PriceReport:
        """Парсить прайс-лист CMD через браузер."""
        start = time.time()
        report = PriceReport(lab="CMD")

        bm = self._bm
        own_bm = False

        try:
            if not bm:
                bm = BrowserManager(headless=True, engine="playwright", stealth="standard")
                await bm.start()
                own_bm = True

            items = await self._parse_via_browser(bm)
            report.items = items

            categories: dict[str, int] = {}
            total = 0
            for item in report.items:
                cat = item.category or "Без категории"
                categories[cat] = categories.get(cat, 0) + 1
                total += item.price

            report.categories = categories
            report.total_price = total

        except Exception as e:
            report.errors.append(str(e))
            logger.error(f"CMD parse error: {e}")

        finally:
            if own_bm and bm:
                await bm.stop()

        report.elapsed_seconds = time.time() - start
        logger.info(f"CMD: {len(report.items)} items, {report.elapsed_seconds:.1f}s")
        return report

    async def _parse_via_browser(self, bm: BrowserManager) -> list[PriceItem]:
        """Парсинг через браузер с ожиданием JS-рендеринга."""
        items = []
        page = await bm.new_page()

        try:
            # Загружаем главную для куки
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Переходим на каталог
            await page.goto(self.CATALOG_URL, wait_until="domcontentloaded", timeout=30000)

            # Ждём появления карточек анализов
            try:
                await page.wait_for_selector(".analyze-item", timeout=15000)
            except:
                logger.warning("CMD: timeout waiting for .analyze-item, proceeding anyway")

            await page.wait_for_timeout(5000)

            # Извлекаем данные через JS
            data = await page.evaluate("""
                () => {
                    const results = [];
                    let currentCategory = '';

                    // Обходим секции
                    const sections = document.querySelectorAll('section.analyze-section, div.analyze-section');
                    for (const section of sections) {
                        const catEl = section.querySelector('h2.analyze-section__title, .analyze-section__title');
                        if (catEl) {
                            currentCategory = catEl.textContent.trim();
                        }

                        const articles = section.querySelectorAll('article.analyze-item, .analyze-item');
                        for (const article of articles) {
                            const titleEl = article.querySelector('.analyze-item__title a') || article.querySelector('.analyze-item__title');
                            const priceEl = article.querySelector('.analyze-item__price');

                            if (titleEl) {
                                const title = titleEl.textContent.trim();
                                const priceText = priceEl ? priceEl.textContent.trim() : '';
                                const price = parseInt(priceText.replace(/[^0-9]/g, '')) || 0;
                                const href = titleEl.href || '';

                                // Извлекаем код и срок из текста карточки
                                const cardText = article.textContent || '';
                                const codeMatch = cardText.match(/Код:\\s*(\\d+)/);
                                const durationMatch = cardText.match(/Срок:\\s*([\\d]+\\s*к\\.д\\.)/);

                                results.push({
                                    title: title,
                                    price: price,
                                    href: href,
                                    category: currentCategory,
                                    code: codeMatch ? codeMatch[1] : '',
                                    duration: durationMatch ? durationMatch[1] : '',
                                });
                            }
                        }
                    }

                    // Если секций нет — ищем просто карточки
                    if (results.length === 0) {
                        const cards = document.querySelectorAll('.analyze-item');
                        for (const card of cards) {
                            const titleEl = card.querySelector('.analyze-item__title a') || card.querySelector('.analyze-item__title');
                            const priceEl = card.querySelector('.analyze-item__price');

                            if (titleEl) {
                                const title = titleEl.textContent.trim();
                                const priceText = priceEl ? priceEl.textContent.trim() : '';
                                const price = parseInt(priceText.replace(/[^0-9]/g, '')) || 0;
                                const href = titleEl.href || '';

                                results.push({ title, price, href, category: '', code: '', duration: '' });
                            }
                        }
                    }

                    return results;
                }
            """)

            if data:
                for entry in data:
                    items.append(PriceItem(
                        lab="CMD",
                        code=str(entry.get("code", "")),
                        name=entry.get("title", "").strip(),
                        price=int(entry.get("price", 0)),
                        duration=str(entry.get("duration", "")).strip(),
                        category=str(entry.get("category", "")).strip(),
                        url=entry.get("href", ""),
                    ))

        finally:
            await page.close()

        return items


# ─── KDL Parser ──────────────────────────────────────────────────────────────

class KDLParser:
    """Парсер прайс-листа KDL (kdl.ru).

    ⚠️ KDL блокирует все запросы (403) даже с браузером.
    Требуется: прокси, mobile UA, или поиск прямого API/PDF.

    Статус: заглушка, парсинг невозможен без дополнительных мер.
    """

    BASE_URL = "https://kdl.ru"
    PRICE_URL = f"{BASE_URL}/analizy-i-tseny/"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def parse(self) -> PriceReport:
        """Парсить прайс-лист KDL (заглушка)."""
        start = time.time()
        report = PriceReport(lab="KDL")
        report.errors.append("KDL блокирует запросы (403). Требуется прокси или обход защиты.")
        report.elapsed_seconds = time.time() - start
        logger.warning("KDL: 403 blocked, skipping")
        return report


# ─── Main Parser ─────────────────────────────────────────────────────────────

class PriceParser:
    """Главный парсер — координирует парсинг всех лабораторий.

    Использование:
        >>> parser = PriceParser()
        >>> all_prices = await parser.parse_all()
        >>> for lab, report in all_prices.items():
        ...     print(f"{lab}: {len(report.items)} анализов, средняя цена {report.avg_price:.0f}р")
    """

    def __init__(self, browser_manager: BrowserManager | None = None):
        self._bm = browser_manager
        self._invitro = InvitroParser()
        self._cmd = CMDParser(browser_manager=browser_manager)
        self._kdl = KDLParser()

    async def parse_all(self) -> dict[str, PriceReport]:
        """Парсить все лаборатории параллельно."""
        results: dict[str, PriceReport] = {}

        # Invitro через HTTP API, CMD через браузер, KDL — заглушка
        bm = self._bm
        own_bm = False

        try:
            if not bm:
                bm = BrowserManager(headless=True, engine="playwright", stealth="standard")
                await bm.start()
                own_bm = True

            cmd_parser = CMDParser(browser_manager=bm)

            invitro_result, cmd_result, kdl_result = await asyncio.gather(
                self._invitro.parse(),
                cmd_parser.parse(),
                self._kdl.parse(),
            )

            results["Invitro"] = invitro_result
            results["CMD"] = cmd_result
            results["KDL"] = kdl_result

        finally:
            if own_bm and bm:
                await bm.stop()

        return results

    async def parse_lab(self, lab: str) -> PriceReport:
        """Парсить конкретную лабораторию.

        Args:
            lab: Название — "Invitro", "CMD", "KDL"
        """
        lab_lower = lab.lower()

        if lab_lower in ("invitro", "инвитро"):
            return await self._invitro.parse()
        elif lab_lower == "cmd":
            return await self._cmd.parse()
        elif lab_lower in ("kdl", "кдл"):
            return await self._kdl.parse()
        else:
            raise ValueError(f"Unknown lab: {lab}. Available: Invitro, CMD, KDL")

    @staticmethod
    def export_to_json(report: PriceReport, filepath: str):
        """Экспортировать отчёт в JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def export_to_csv(report: PriceReport, filepath: str):
        """Экспортировать отчёт в CSV."""
        import csv
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Код", "Название", "Цена", "Валюта", "Срок", "Категория", "URL"])
            for item in report.items:
                writer.writerow([
                    item.code, item.name, item.price, item.currency,
                    item.duration, item.category, item.url,
                ])
