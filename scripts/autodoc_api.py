#!/usr/bin/env python3
"""
autodoc.ru Parser — через публичное API (без браузера)

Рабочие endpoints (подтверждено):

БЕЗ АВТОРИЗАЦИИ:
  GET /api/price-service/search/manufacturers?article={article}
    → {items: [{article, manufacturer: {name, id}, goodsName, imageUrl}]}

  GET /api/goods-service/goods/price?article={article}&manufacturerId={id}
    → {minimalPrice, minimalDeliveryDays}

  GET /api/goods-service/goods/info?article={article}&manufacturerId={id}
    → {article, name, fullName, categoryId, manufacturer, rating, imageUrls, items: [{name, value, unit}]}

  GET /api/goods-service/manufacturers/groups
    → {items: [{letter, manufacturers: [{name, id}]}]}

  GET /api/goods-service/manufacturers/{id}/info
    → {name, description, ...}

  GET /api/catalog-service/cars/brands
    → {popularItems: [{name, id}]}

C АВТОРИЗАЦИЕЙ (Bearer token через OIDC password grant):
  POST https://login.autodoc.ru/connect/token
    → {access_token, expires_in, token_type, refresh_token}

  Требуемый scope для price-list: "openid offline_access ProductService BasketService"

  GET /api/price-service/price-list/goods-info?article={article}&manufacturerId={id}
    → {manufacturerName, article, displayArticle, goodsName, commentCount, ratingAverage}

  Остальные price-list/* endpoints (analogs, originals, access-levels, price-history)
  возвращают 500 — требуют полноценный аккаунт с профилем (shopId, priceLevel и т.д.)
"""

import time
from dataclasses import dataclass, field

import requests


# ──────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────


@dataclass
class Manufacturer:
    name: str
    id: int


@dataclass
class Offer:
    """Одно предложение (аналог) запчасти"""

    manufacturer: Manufacturer
    article: str
    goods_name: str
    price: float | None = None
    delivery_days: int | None = None
    in_stock: int | None = None
    image_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class PartInfo:
    """Полная информация о запчасти"""

    article: str
    name: str
    full_name: str
    manufacturer: Manufacturer | None = None
    category_id: int | None = None
    rating_avg: float = 0.0
    rating_count: int = 0
    image_urls: list = field(default_factory=list)
    properties: list = field(default_factory=list)  # [{name, value, unit}]
    offers: list = field(default_factory=list)  # [Offer]
    raw: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
#  API Client
# ──────────────────────────────────────────────


class AutodocAPI:
    BASE = "https://web.autodoc.ru"
    TOKEN_URL = "https://login.autodoc.ru/connect/token"

    def __init__(self, username: str = None, password: str = None):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.autodoc.ru/",
            }
        )
        self._token = None
        self._token_expires = 0

        # Visit main page to get cookies
        try:
            self.session.get("https://www.autodoc.ru/", timeout=10)
        except Exception:
            pass

        if username and password:
            self._authenticate(username, password)

    def _authenticate(self, username: str, password: str):
        """OIDC Resource Owner Password Credentials grant"""
        r = self.session.post(
            self.TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": "Angular",
                "username": username,
                "password": password,
                "scope": "openid offline_access ProductService BasketService OrderService",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600) - 60
        self.session.headers["Authorization"] = f"Bearer {self._token}"

    def _ensure_auth(self):
        if self._token and time.time() < self._token_expires:
            return
        if self._token:
            # Try refresh
            r = self.session.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": "Angular",
                    "refresh_token": self._get_refresh_token(),
                    "scope": "openid offline_access ProductService BasketService",
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                self._token = data["access_token"]
                self._token_expires = time.time() + data.get("expires_in", 3600)
                self.session.headers["Authorization"] = f"Bearer {self._token}"
                return
        raise RuntimeError("Expired token and no refresh available")

    def _get_refresh_token(self):
        return getattr(self, "_refresh_token", "")

    # ── Public API (no auth needed) ──

    def search_manufacturers(self, article: str) -> list[dict]:
        """
        Поиск производителей по артикулу.
        GET /api/price-service/search/manufacturers?article={article}

        Возвращает список:
        [{article, manufacturer: {name, id}, goodsName, imageUrl}]
        """
        r = self.session.get(
            f"{self.BASE}/api/price-service/search/manufacturers",
            params={"article": article},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def get_goods_price(self, article: str, manufacturer_id: int) -> dict:
        """
        Минимальная цена и сроки доставки.
        GET /api/goods-service/goods/price?article=X&manufacturerId=Y

        Возвращает: {minimalPrice, minimalDeliveryDays}
        """
        r = self.session.get(
            f"{self.BASE}/api/goods-service/goods/price",
            params={"article": article, "manufacturerId": manufacturer_id},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_goods_info(self, article: str, manufacturer_id: int) -> dict:
        """
        Полная информация о товаре.
        GET /api/goods-service/goods/info?article=X&manufacturerId=Y

        Возвращает: {article, name, fullName, categoryId, manufacturer, rating,
                      imageUrls, items: [{name, value, unit}]}
        """
        r = self.session.get(
            f"{self.BASE}/api/goods-service/goods/info",
            params={"article": article, "manufacturerId": manufacturer_id},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_manufacturer_info(self, manufacturer_id: int) -> dict:
        """
        Информация о производителе.
        GET /api/goods-service/manufacturers/{id}/info
        """
        r = self.session.get(
            f"{self.BASE}/api/goods-service/manufacturers/{manufacturer_id}/info",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_manufacturer_groups(self) -> dict:
        """
        Все группы производителей (по буквам).
        GET /api/goods-service/manufacturers/groups

        Возвращает: {items: [{letter, manufacturers: [{name, id}]}]}
        """
        r = self.session.get(
            f"{self.BASE}/api/goods-service/manufacturers/groups",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_car_brands(self) -> dict:
        """
        Каталог марок авто.
        GET /api/catalog-service/cars/brands

        Возвращает: {popularItems: [{name, id, supportWizardSearch}]}
        """
        r = self.session.get(
            f"{self.BASE}/api/catalog-service/cars/brands",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_car_models(self, brand_id: int) -> dict:
        """
        Модели авто по марке.
        GET /api/catalog-service/cars/models?brandId={id}
        """
        r = self.session.get(
            f"{self.BASE}/api/catalog-service/cars/models",
            params={"brandId": brand_id},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ── Authenticated API ──

    def get_price_list_goods_info(self, article: str, manufacturer_id: int) -> dict:
        """
        Инфо о товаре из прайс-листа (требует авторизацию).
        GET /api/price-service/price-list/goods-info?article=X&manufacturerId=Y

        Возвращает: {manufacturerName, article, displayArticle, goodsName,
                      commentCount, ratingAverage}
        """
        self._ensure_auth()
        r = self.session.get(
            f"{self.BASE}/api/price-service/price-list/goods-info",
            params={"article": article, "manufacturerId": manufacturer_id},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ── High-level helpers ──

    def search_part(self, article: str) -> PartInfo:
        """
        Полный поиск запчасти: производители, цены, характеристики.
        Работает БЕЗ авторизации.
        """
        # Шаг 1: найти производителей
        mnf_list = self.search_manufacturers(article)
        if not mnf_list:
            raise ValueError(f"Article {article}: no manufacturers found")

        offers = []
        first_info = None

        for item in mnf_list:
            mnf_name = item.get("manufacturer", {}).get("name", "")
            mnf_id = item.get("manufacturer", {}).get("id", 0)
            goods_name = item.get("goodsName", "")
            image_url = item.get("imageUrl")

            # Шаг 2: цена
            price_data = {}
            try:
                price_data = self.get_goods_price(article, mnf_id)
            except Exception:
                pass

            # Шаг 3: инфо о товаре (только для первого)
            info_data = {}
            if first_info is None:
                try:
                    info_data = self.get_goods_info(article, mnf_id)
                    first_info = info_data
                except Exception:
                    pass

            offer = Offer(
                manufacturer=Manufacturer(name=mnf_name, id=mnf_id),
                article=article,
                goods_name=goods_name,
                price=price_data.get("minimalPrice"),
                delivery_days=price_data.get("minimalDeliveryDays"),
                image_url=image_url,
                raw={"price": price_data, "info": info_data},
            )
            offers.append(offer)

        # Формируем PartInfo
        if first_info:
            return PartInfo(
                article=article,
                name=first_info.get("name", ""),
                full_name=first_info.get("fullName", ""),
                manufacturer=offers[0].manufacturer if offers else None,
                category_id=first_info.get("categoryId"),
                rating_avg=first_info.get("rating", {}).get("average", 0),
                rating_count=first_info.get("rating", {}).get("quantity", 0),
                image_urls=first_info.get("imageUrls", []),
                properties=first_info.get("items", []),
                offers=offers,
                raw=first_info,
            )
        else:
            return PartInfo(
                article=article,
                name=offers[0].goods_name if offers else "",
                full_name="",
                offers=offers,
            )


# ──────────────────────────────────────────────
#  CLI / Demo
# ──────────────────────────────────────────────


def main():
    import sys

    article = sys.argv[1] if len(sys.argv) > 1 else "OC471"

    print("=== autodoc.ru API Parser ===")
    print(f"Article: {article}\n")

    api = AutodocAPI()

    # 1. Search manufacturers
    print("1. Поиск производителей...")
    mnfs = api.search_manufacturers(article)
    print(f"   Найдено: {len(mnfs)} производителей")
    for m in mnfs[:5]:
        print(f"   - {m['manufacturer']['name']} (id={m['manufacturer']['id']}): {m['goodsName']}")
    print()

    # 2. Get prices for each
    print("2. Цены и сроки доставки...")
    for m in mnfs[:5]:
        mnf_id = m["manufacturer"]["id"]
        mnf_name = m["manufacturer"]["name"]
        try:
            price = api.get_goods_price(article, mnf_id)
            print(
                f"   {mnf_name}: {price['minimalPrice']} руб, {price['minimalDeliveryDays']} дней"
            )
        except Exception as e:
            print(f"   {mnf_name}: ошибка — {e}")
    print()

    # 3. Full info for first manufacturer
    if mnfs:
        mnf_id = mnfs[0]["manufacturer"]["id"]
        print(f"3. Полная инфо (производитель: {mnfs[0]['manufacturer']['name']})...")
        try:
            info = api.get_goods_info(article, mnf_id)
            print(f"   Название: {info.get('fullName', info.get('name', '?'))}")
            rating = info.get("rating", {})
            print(f"   Рейтинг: {rating.get('average', 0)} ({rating.get('quantity', 0)} отзывов)")
            print(f"   В наличии: {info.get('inStock', '?')}")
            props = info.get("items", [])
            if props:
                print("   Характеристики:")
                for p in props[:8]:
                    print(f"     {p['name']}: {p['value']} {p['unit']}")
        except Exception as e:
            print(f"   Ошибка: {e}")
    print()

    # 4. One-shot search_part()
    print("4. Полный поиск (search_part)...")
    try:
        result = api.search_part(article)
        print(f"   Название: {result.full_name}")
        print(f"   Предложений: {len(result.offers)}")
        for o in result.offers[:5]:
            print(f"   - {o.manufacturer.name}: {o.price} руб, {o.delivery_days} дней")
    except Exception as e:
        print(f"   Ошибка: {e}")


if __name__ == "__main__":
    main()
