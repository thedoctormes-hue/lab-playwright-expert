"""
AvitoDealerSpider — парсер дилерских объявлений на Авито.

Парсит карточки авто с селекторами:
- title: [data-marker="item-title"] / [itemprop="name"]
- price: [data-marker="item-price"] / [data-marker="item-price-value"]
- params: [data-marker="item-specific-params"] (пробег, объём, КПП, привод)
- location: [data-marker="item-location"]
- date: [data-marker="item-date"]
- link: a[itemprop="url"]
- images: [data-marker="slider-image"] img src
- badge: .SnippetBadgeV2-root (дилер/проверен/трейд-ин)

Использование:
    python -m lab_playwright_kit.scrapy_engine.scripts.run_spider avito_dealer \
        --brand toyota --year_from 2020 --max_pages 3 --output ./reports/avito_dealer.json
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from loguru import logger


# ── URL-_builder для дилерских фильтров ──
AVITO_BASE = "https://www.avito.ru/moskva/avtomobili"


def build_dealer_url(
    brand: str = "",
    model: str = "",
    year_from: int = 0,
    year_to: int = 0,
    price_from: int = 0,
    price_to: int = 0,
    page: int = 1,
) -> str:
    """Собрать URL Авито с фильтрами по бренду/году/цене."""
    params: dict[str, str] = {}
    if brand:
        params["q"] = brand
    if year_from:
        params["year_from"] = str(year_from)
    if year_to:
        params["year_to"] = str(year_to)
    if price_from:
        params["price_from"] = str(price_from)
    if price_to:
        params["price_to"] = str(price_to)
    if page > 1:
        params["p"] = str(page)

    params["s"] = "104"  # sort by date (newest first)

    return f"{AVITO_BASE}?{urlencode(params)}" if params else AVITO_BASE


# ── Парсинг цены: "1 750 000 ₽" → 1750000 ──
def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


# ── Парсинг параметров: "170 000 км, 1.6 AT (123 л.с.), седан, передний, бензин" ──
def parse_params(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not text:
        return result

    parts = [p.strip() for p in text.split(",")]

    for part in parts:
        # Пробег
        m = re.search(r"(\d[\d\s]*)\s*км", part)
        if m:
            result["mileage_km"] = m.group(1).replace(" ", "")

        # Объём двигателя + тип КПП
        m = re.search(r"(\d+\.\d+)\s*(AT|MT|AMT|CVT|Робот)", part)
        if m:
            result["engine_L"] = m.group(1)
            result["transmission"] = m.group(2)

        # Мощность
        m = re.search(r"(\d+)\s*л\.с\.", part)
        if m:
            result["power_hp"] = m.group(1)

        # Тип кузова
        for body in [
            "седан",
            "хэтчбек",
            "внедорожник",
            "кроссовер",
            "универсал",
            "купе",
            "минивэн",
            "пикап",
            "лифтбек",
        ]:
            if body in part.lower():
                result["body_type"] = body
                break

        # Привод
        for drive in ["передний", "задний", "полный"]:
            if drive in part.lower():
                result["drive"] = drive
                break

        # Топливо
        for fuel in ["бензин", "дизель", "гибрид", "электро"]:
            if fuel in part.lower():
                result["fuel"] = fuel
                break

    return result


# ── Парсинг даты: "Вчера" / "Сегодня" / "2 дня назад" ──
def parse_date_ru(text: str, now: datetime | None = None) -> str:
    if not text:
        return ""
    now = now or datetime.now()
    text = text.strip().lower()
    if "сегодня" in text:
        return now.strftime("%Y-%m-%d")
    if "вчера" in text:
        from datetime import timedelta

        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*(?:день|дня|дней|час|часа|часов)", text)
    if m:
        from datetime import timedelta

        n = int(m.group(1))
        if "час" in text:
            date = now - timedelta(hours=n)
        else:
            date = now - timedelta(days=n)
        return date.strftime("%Y-%m-%d")
    return text


# ── Основная функция парсинга (без Scrapy) — для быстрого запуска ──
def parse_avito_listing(
    html: str,
    source_url: str = "",
    brand: str = "",
) -> list[dict[str, Any]]:
    """Распарсить HTML страницы Авито и вернуть список авто."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('[data-marker="item"]')
    results: list[dict[str, Any]] = []
    now = datetime.now()

    for card in cards:
        # Заголовок
        title_el = card.select_one('[data-marker="item-title"]') or card.select_one(
            '[itemprop="name"]'
        )
        title = title_el.text.strip() if title_el else ""
        if not title:
            continue

        # Цена
        price_el = (
            card.select_one('[data-marker="item-price-value"]')
            or card.select_one('[data-marker="item-price"]')
            or card.select_one('[itemprop="price"]')
        )
        price_text = price_el.text.strip() if price_el else ""
        price = parse_price(price_text)

        # Параметры
        params_el = card.select_one('[data-marker="item-specific-params"]')
        params_text = params_el.text.strip() if params_el else ""
        params = parse_params(params_text)

        # Локация
        loc_el = card.select_one('[data-marker="item-location"]')
        location = loc_el.text.strip() if loc_el else ""

        # Дата
        date_el = card.select_one('[data-marker="item-date"]')
        date_text = date_el.text.strip() if date_el else ""
        date = parse_date_ru(date_text, now)

        # Ссылка
        link_el = card.select_one('a[itemprop="url"]') or card.select_one(
            'a[href*="/moskva/avtomobili/"]'
        )
        link = "https://www.avito.ru" + link_el["href"] if link_el else ""

        # Изображения
        images = []
        for img in card.select('[data-marker^="slider-image"] img[src]'):
            src = img.get("src", "")
            if src.startswith("http"):
                images.append(src)
        # Fallback: просто все img внутри карточки
        if not images:
            for img in card.select("img[src]"):
                src = img.get("src", "")
                if src.startswith("http") and "avito" in src:
                    images.append(src)
                    break  # первая фотка

        # Бейджи (дилер/проверено)
        badges = []
        for b in card.select('[class*="SnippetBadge"]'):
            btxt = b.text.strip()
            if btxt:
                badges.append(btxt)

        # Год из заголовка
        year_m = re.search(r"\b(19|20)\d{2}\b", title)
        year = int(year_m.group()) if year_m else params.get("year", 0)

        item = {
            "title": title,
            "brand": brand or title.split()[0] if title else "",
            "year": year,
            "price_rub": price,
            "price_formatted": price_text,
            "mileage_km": params.get("mileage_km", ""),
            "engine_L": params.get("engine_L", ""),
            "transmission": params.get("transmission", ""),
            "power_hp": params.get("power_hp", ""),
            "body_type": params.get("body_type", ""),
            "drive": params.get("drive", ""),
            "fuel": params.get("fuel", ""),
            "location": location,
            "date": date,
            "url": link,
            "images": images[:3],  # макс 3 фото
            "badges": badges,
            "source": "avito.ru",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "listing_url": source_url,
        }
        results.append(item)

    logger.info(f"Parsed {len(results)} cars from Avito HTML")
    return results


def parse_avito_pages(
    pages_dir: str,
    brand: str = "",
) -> list[dict[str, Any]]:
    """Распарсить сохранённые HTML-страницы."""
    import glob

    results: list[dict[str, Any]] = []
    files = sorted(glob.glob(str(Path(pages_dir) / "*.html")))
    for f in files:
        with open(f, encoding="utf-8") as fh:
            html = fh.read()
        results.extend(parse_avito_listing(html, f"file://{f}", brand))
    logger.info(f"Parsed {len(results)} cars from {len(files)} pages")
    return results


# === Scrapy Spider ===

from scrapy import Request, Spider


class AvitoDealerSpider(Spider):
    """Scrapy Spider — парсинг дилерских объявлений Avito."""

    name = "avito_dealer"
    allowed_domains = ["avito.ru"]

    def __init__(self, url: str = "", brand: str = "", max_pages: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.start_urls = [url] if url else []
        self.brand = brand
        self.max_pages = int(max_pages)

    def parse(self, response):
        cars = parse_avito_listing(response.text, response.url, self.brand)
        for car in cars:
            yield car

        # Пагинация
        if self.max_pages > 1:
            next_page = response.css('a[aria-label="Следующая"]::attr(href)').get()
            if next_page:
                self.max_pages -= 1
                yield Request(url=response.urljoin(next_page), callback=self.parse)
