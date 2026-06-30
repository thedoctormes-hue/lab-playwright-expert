"""PlaywrightPartSpider — универсальный паук для магазинов автозапчастей.

Каждый магазин (emex, exist, apex, fobil, autoeuro, mymajor, autodoc)
описывается конфигурацией в auto_parts/__init__.py.

Поддерживает три метода поиска:
  1. url_param — GET-запрос с артикулом в URL (emex, exist, fobil)
  2. form_submit — открыть базовый URL, ввести артикул в форму (apex, autoeuro, mymajor)
  3. api — прямые вызовы REST API без браузера (autodoc)

JS-рендеринг (url_param, form_submit) → scrapy-playwright.
API метод → чистые HTTP-запросы через requests.

Результат: ScrapedPart items, совместимые с PriceResult из AutoExpert.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import requests
from loguru import logger
from scrapy import Request, Spider
from scrapy.http import Response

from lab_playwright_kit.scrapy_engine.items import ScrapedPart
from lab_playwright_kit.scrapy_engine.spiders.auto_parts import SHOP_CONFIGS


# ─── Helper ───────────────────────────────────────────────────────────────────


def parse_price(text: str) -> float:
    """Извлечь число из текста цены."""
    if not text:
        return 0.0
    # Убираем всё кроме цифр, точки и запятой
    cleaned = re.sub(r"[^\d.,]", "", text.replace(" ", ""))
    # Заменяем запятую на точку
    cleaned = cleaned.replace(",", ".")
    # Если несколько точек — оставляем последнюю
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def parse_delivery_days(text: str) -> int | None:
    """Извлечь количество дней доставки из текста."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


# ─── Spider ───────────────────────────────────────────────────────────────────


class PlaywrightPartSpider(Spider):
    """Универсальный паук для магазинов автозапчастей через Playwright."""

    name = "auto_parts"
    allowed_domains = [
        "emex.ru",
        "www.emex.ru",
        "exist.ru",
        "apex.ru",
        "fobil-auto.ru",
        "shop.autoeuro.ru",
        "mymajor.ru",
        "www.autodoc.ru",
    ]

    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
        },
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],
        "DOWNLOADER_MIDDLEWARES": {
            "lab_playwright_kit.scrapy_engine.middlewares.StealthMiddleware": 400,
        },
        "ITEM_PIPELINES": {
            "lab_playwright_kit.scrapy_engine.pipelines.ValidationPipeline": 100,
            "lab_playwright_kit.scrapy_engine.pipelines.DedupPipeline": 200,
        },
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": ["--no-sandbox"],
        },
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30000,
    }

    def __init__(
        self,
        article: str = "",
        shops: str = "",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.article = article.strip().upper()
        self.slug = re.sub(r"[^A-Z0-9\-]", "", self.article) or "TEST"

        # Определяем, какие магазины парсить
        if shops:
            self.shop_keys = [s.strip() for s in shops.split(",") if s.strip() in SHOP_CONFIGS]
        else:
            self.shop_keys = list(SHOP_CONFIGS.keys())

        logger.info(f"[PartSpider] Артикул: {article}, магазины: {self.shop_keys}")

    def start_requests(self):
        """Синхронный alias для unit тестов и Scrapy < 2.13."""
        import asyncio

        async def _collect():
            results = []
            async for item in self.start():
                results.append(item)
            return results

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_collect())
        finally:
            loop.close()

    async def start(self) -> AsyncIterator[Request]:
        """Начальная точка — генерируем запросы для каждого магазина."""
        for shop_key in self.shop_keys:
            config = SHOP_CONFIGS[shop_key]
            meta = {
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_methods": [],
                "shop_key": shop_key,
                "article": self.article,
                "slug": self.slug,
            }

            if config["search_method"] == "url_param" and config["search_url"]:
                url = config["search_url"].format(article=self.article)
                yield Request(
                    url=url,
                    callback=self.parse_results,
                    meta=meta,
                    errback=self.errback,
                    dont_filter=True,
                )
            elif config["search_method"] == "form_submit":
                yield Request(
                    url=config["base_url"],
                    callback=self.submit_search_form,
                    meta=meta,
                    errback=self.errback,
                    dont_filter=True,
                )
            elif config["search_method"] == "api":
                # API-метод: вызываем напрямую, без Playwright
                async for item in self._parse_api(shop_key, config, self.article):
                    yield item

    # ─── URL-based search (emex, exist, fobil, autodoc) ──────────────────────

    async def parse_results(self, response: Response) -> AsyncIterator[ScrapedPart]:
        """Парсинг страницы результатов поиска."""
        shop_key = response.meta["shop_key"]
        article = response.meta["article"]
        config = SHOP_CONFIGS[shop_key]
        page = response.meta.get("playwright_page")
        selectors = config["selectors"]

        logger.info(f"[{shop_key}] Парсинг результатов: {response.url}")

        # Даём JS время отрендерить
        if page:
            await page.wait_for_timeout(3000)

        results = []

        # Специфичная логика для каждого магазина
        if shop_key == "exist":
            results = await self._parse_exist(response, page, article, config)
        elif shop_key == "fobil":
            results = await self._parse_fobil(response, page, article, config)
        else:
            # Универсальный парсинг через CSS-селекторы
            results = await self._parse_generic(response, page, article, config)

        logger.info(f"[{shop_key}] Найдено: {len(results)}")
        for item in results:
            yield item

    async def _parse_generic(
        self,
        response: Response,
        page: Any,
        article: str,
        config: dict,
    ) -> list[ScrapedPart]:
        """Универсальный парсинг через CSS-селекторы."""
        results = []
        selectors = config["selectors"]
        now = datetime.now(timezone.utc).isoformat()

        if not page:
            return results

        # Определяем селектор строки результата
        row_selector = selectors.get("result_row") or selectors.get("result_item", "table tr")
        rows = await page.query_selector_all(row_selector)
        logger.debug(f"[{config.get('display', '?')}] Строк: {len(rows)}")

        for row in rows[:10]:
            try:
                price_el = await row.query_selector(selectors.get("price", ".price"))
                if not price_el:
                    continue

                price_text = await price_el.inner_text()
                price = parse_price(price_text)
                if price <= 0:
                    continue

                name = article
                name_selector = selectors.get("name")
                if name_selector:
                    name_el = await row.query_selector(name_selector)
                    if name_el:
                        raw = (await name_el.inner_text()).strip()
                        if raw:
                            name = raw[:200]

                product_url = response.url
                link_el = await row.query_selector("a[href]")
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href:
                        base = config["base_url"]
                        product_url = href if href.startswith("http") else f"{base}{href}"

                item = ScrapedPart(
                    url=response.url,
                    domain=config["base_url"].replace("https://", "").replace("http://", ""),
                    spider_name=self.name,
                    article=article,
                    name=name,
                    brand="",
                    price=price,
                    currency="RUB",
                    availability="unknown",
                    shop_name=config["display"],
                    product_url=product_url,
                    crawl_time=now,
                    status_code=response.status,
                )
                results.append(item)

            except Exception as e:
                logger.debug(f"[{config.get('display', '?')}] row error: {e}")

        return results

    async def _parse_exist(
        self,
        response: Response,
        page: Any,
        article: str,
        config: dict,
    ) -> list[ScrapedPart]:
        """Специфичный парсинг Exist.ru — .price-wrapper + fallback на table."""
        results = []
        selectors = config["selectors"]
        now = datetime.now(timezone.utc).isoformat()

        if not page:
            return results

        # Ждём появления цен
        try:
            await page.wait_for_selector(".price-wrapper", timeout=15000)
        except Exception:
            logger.debug("[exist] .price-wrapper не найден, fallback на table")

        wrappers = await page.query_selector_all(selectors.get("result_row", ".price-wrapper"))

        for wrapper in wrappers[:10]:
            try:
                price_el = await wrapper.query_selector(selectors.get("price", ".price"))
                if not price_el:
                    continue

                price_text = await price_el.inner_text()
                price = parse_price(price_text)
                if price <= 0:
                    continue

                brand = ""
                brand_el = await wrapper.query_selector(selectors.get("brand", ".caseBrand"))
                if brand_el:
                    brand = (await brand_el.inner_text()).strip()

                name = article
                name_el = await wrapper.query_selector(selectors.get("name", ".caseDescription"))
                if name_el:
                    raw = (await name_el.inner_text()).strip()
                    if raw:
                        name = raw

                delivery = None
                del_el = await wrapper.query_selector(selectors.get("delivery", ""))
                if del_el:
                    delivery = parse_delivery_days(await del_el.inner_text())

                item = ScrapedPart(
                    url=response.url,
                    domain="exist.ru",
                    spider_name=self.name,
                    article=article,
                    name=name,
                    brand=brand,
                    price=price,
                    currency="RUB",
                    availability="unknown",
                    delivery_days=delivery,
                    shop_name="Exist.ru",
                    product_url=response.url,
                    crawl_time=now,
                    status_code=response.status,
                )
                results.append(item)

            except Exception as e:
                logger.debug(f"[exist] row error: {e}")

        # Fallback на таблицу
        if not results:
            fallback_rows = await page.query_selector_all(selectors.get("fallback_row", "table tr"))
            for row in fallback_rows[:20]:
                try:
                    price_el = await row.query_selector(
                        selectors.get("fallback_price", "td .price")
                    )
                    if not price_el:
                        continue
                    price = parse_price(await price_el.inner_text())
                    if price <= 0:
                        continue

                    name = article
                    name_el = await row.query_selector(
                        selectors.get("fallback_name", "td:first-child")
                    )
                    if name_el:
                        raw = (await name_el.inner_text()).strip()
                        if raw:
                            name = raw

                    results.append(
                        ScrapedPart(
                            url=response.url,
                            domain="exist.ru",
                            spider_name=self.name,
                            article=article,
                            name=name,
                            brand="",
                            price=price,
                            currency="RUB",
                            availability="unknown",
                            shop_name="Exist.ru",
                            product_url=response.url,
                            crawl_time=now,
                            status_code=response.status,
                        )
                    )
                except Exception:
                    continue

        return results

    async def _parse_fobil(
        self,
        response: Response,
        page: Any,
        article: str,
        config: dict,
    ) -> list[ScrapedPart]:
        """Специфичный парсинг Fobil-Auto.ru — tr.startSearching."""
        results = []
        selectors = config["selectors"]
        now = datetime.now(timezone.utc).isoformat()

        if not page:
            return results

        try:
            await page.wait_for_selector(
                selectors.get("result_row", "tr.startSearching"), timeout=10000
            )
        except Exception:
            await page.wait_for_timeout(3000)

        rows = await page.query_selector_all(selectors.get("result_row", "tr.startSearching"))
        logger.debug(f"[fobil] Строк: {len(rows)}")

        for row in rows[:10]:
            try:
                price_el = await row.query_selector(selectors.get("price", ".casePrices"))
                if not price_el:
                    continue

                price = parse_price(await price_el.inner_text())
                if price <= 0:
                    continue

                brand = ""
                brand_el = await row.query_selector(selectors.get("brand", ".caseBrand"))
                if brand_el:
                    brand = (await brand_el.inner_text()).strip()

                name = article
                name_el = await row.query_selector(selectors.get("name", ".caseDescription"))
                if name_el:
                    raw = (await name_el.inner_text()).strip()
                    if raw:
                        name = raw

                results.append(
                    ScrapedPart(
                        url=response.url,
                        domain="fobil-auto.ru",
                        spider_name=self.name,
                        article=article,
                        name=name,
                        brand=brand,
                        price=price,
                        currency="RUB",
                        availability="unknown",
                        shop_name="Fobil-Auto",
                        product_url=response.url,
                        crawl_time=now,
                        status_code=response.status,
                    )
                )

            except Exception as e:
                logger.debug(f"[fobil] row error: {e}")

        return results

    # ─── Form-based search (apex, autoeuro, mymajor) ─────────────────────────

    async def submit_search_form(self, response: Response) -> AsyncIterator[ScrapedPart]:
        """Открыть страницу, ввести артикул в форму поиска, дождаться результатов."""
        shop_key = response.meta["shop_key"]
        article = response.meta["article"]
        config = SHOP_CONFIGS[shop_key]
        page = response.meta.get("playwright_page")

        if not page:
            logger.warning(f"[{shop_key}] Playwright page недоступна")
            return

        logger.info(f"[{shop_key}] Отправка формы поиска")

        try:
            input_sel = config["selectors"].get("search_input", 'input[type="search"]')
            search_input = await page.query_selector(input_sel)

            if search_input:
                await search_input.fill(article)
                await search_input.press("Enter")
                await page.wait_for_timeout(5000)
            else:
                logger.warning(f"[{shop_key}] Поле поиска не найдено: {input_sel}")
                return

            # Теперь парсим результаты как универсальным способом
            meta = dict(response.meta)
            new_response = response.replace(url=page.url)
            async for item in self.parse_results(new_response):
                yield item

        except Exception as e:
            logger.error(f"[{shop_key}] Ошибка формы: {e}")

    # ─── API-based search (autodoc) ─────────────────────────────────────────

    async def _parse_api(
        self, shop_key: str, config: dict, article: str
    ) -> AsyncIterator[ScrapedPart]:
        """API-метод: прямые HTTP-запросы без браузера."""
        if shop_key == "autodoc":
            async for item in self._parse_autodoc_api(article, config):
                yield item
        else:
            logger.warning(f"[{shop_key}] API-метод не реализован")

    async def _parse_autodoc_api(self, article: str, config: dict) -> AsyncIterator[ScrapedPart]:
        """
        Парсинг autodoc.ru через публичное API.

        Использует:
          GET /api/price-service/search/manufacturers?article={article}
          GET /api/goods-service/goods/price?article=X&manufacturerId=Y
          GET /api/goods-service/goods/info?article=X&manufacturerId=Y

        Все endpoints публичные, не требуют авторизации.
        """
        api_base = config.get("api_base", "https://web.autodoc.ru")
        now = datetime.now(timezone.utc).isoformat()

        logger.info(f"[autodoc] API-парсинг артикула: {article}")

        try:
            # Шаг 1: поиск производителей
            r = requests.get(
                f"{api_base}/api/price-service/search/manufacturers",
                params={"article": article},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Referer": "https://www.autodoc.ru/",
                },
                timeout=10,
            )
            r.raise_for_status()
            mnfs = r.json().get("items", [])
            logger.info(f"[autodoc] Найдено производителей: {len(mnfs)}")

            if not mnfs:
                logger.info(f"[autodoc] Артикул {article}: производители не найдены")
                return

            # Шаг 2: для каждого производителя — цена и инфо
            for item in mnfs:
                mnf_name = item.get("manufacturer", {}).get("name", "")
                mnf_id = item.get("manufacturer", {}).get("id", 0)
                goods_name = item.get("goodsName", article)
                image_url = item.get("imageUrl")

                # Цена
                price = 0.0
                delivery_days = None
                try:
                    pr = requests.get(
                        f"{api_base}/api/goods-service/goods/price",
                        params={"article": article, "manufacturerId": mnf_id},
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                        timeout=10,
                    )
                    if pr.status_code == 200:
                        price_data = pr.json()
                        price = price_data.get("minimalPrice", 0) or 0
                        delivery_days = price_data.get("minimalDeliveryDays")
                except Exception as e:
                    logger.debug(f"[autodoc] price error for {mnf_name}: {e}")

                # Полная инфо (только для первого с ценой > 0)
                name = goods_name or article

                yield ScrapedPart(
                    url=f"https://www.autodoc.ru/search?query={article}",
                    domain="autodoc.ru",
                    spider_name=self.name,
                    article=article,
                    name=name,
                    brand=mnf_name,
                    price=float(price),
                    currency="RUB",
                    availability="in_stock" if price > 0 else "unknown",
                    delivery_days=delivery_days,
                    shop_name="Autodoc.ru",
                    product_url=f"https://www.autodoc.ru/search?query={article}",
                    image_url=image_url,
                    crawl_time=now,
                    status_code=200,
                )

        except requests.HTTPError as e:
            logger.error(f"[autodoc] HTTP ошибка: {e}")
        except Exception as e:
            logger.error(f"[autodoc] Ошибка API: {e}")

    # ─── Error handling ─────────────────────────────────────────────────────

    def errback(self, failure):
        """Обработка ошибок запроса."""
        shop = failure.request.meta.get("shop_key", "?")
        logger.error(f"[{shop}] Ошибка запроса: {failure.value}")
