"""
DataParser — универсальный адаптер парсинга данных под разные ниши.

Расширяет PageParser с:
- Декларативные схемы извлечения (SchemaExtractor)
- Предустановленные профили для популярных ниш (NicheProfile)
- Пост-обработка и нормализация данных
- Экспорт в разных форматах (JSON, CSV, dict)

Профили ниш:
- e-commerce: товары, цены, отзывы, рейтинги
- news: статьи, авторы, даты, категории
- realty: объявления недвижимости, цена, площадь, адрес
- medtech: медицинские статьи, препараты, клиники
- jobs: вакансии, зарплата, компания, требования
- auto: объявления авто, цена, год, пробег
- habr: статьи Хабра, автор, рейтинг, хабы, теги
- vcru: статьи VC.ru, автор, рейтинг, категории
- twitter: твиты, автор, лайки, ретвиты, хэштеги
- telegram: посты каналов, текст, просмотры, реакции
- custom: пользовательская схема

Использование:
    >>> from lab_playwright_kit.data_parser import DataParser, NicheProfile
    >>> parser = DataParser(browser_manager, profile=NicheProfile.ECOMMERCE)
    >>> result = await parser.parse_product_page("https://shop.example.com/product/123")
    >>> print(result["price"], result["title"])
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Page

from .parser import PageParser, ParsedContent


# ─── Niche Profiles ──────────────────────────────────────────────────────────

class NicheType(str, Enum):
    """Типы ниш для парсинга."""
    ECOMMERCE = "ecommerce"
    NEWS = "news"
    REALTY = "realty"
    MEDTECH = "medtech"
    JOBS = "jobs"
    AUTO = "auto"
    HABR = "habr"
    VCRU = "vcru"
    TWITTER = "twitter"
    TELEGRAM = "telegram"
    CUSTOM = "custom"
    GENERIC = "generic"


@dataclass
class FieldMapping:
    """Маппинг одного поля данных.

    Attributes:
        name: Имя поля в результате
        selectors: Список CSS-селекторов (пробуются по порядку)
        attribute: HTML-атрибут для извлечения (None = inner_text)
        regex: Регулярка для пост-обработки
        transform: Функция трансформации (callable)
        default: Значение по умолчанию
        required: Обязательное поле
        is_list: Извлечь все совпадения
        description: Описание поля
    """
    name: str
    selectors: list[str] = field(default_factory=list)
    attribute: str | None = None
    regex: str | None = None
    transform: str | None = None  # "int", "float", "date", "strip", "lowercase"
    default: Any = None
    required: bool = False
    is_list: bool = False
    description: str = ""


@dataclass
class NicheSchema:
    """Схема парсинга для конкретной ниши.

    Attributes:
        niche: Тип ниши
        name: Человекочитаемое имя
        description: Описание
        fields: Список маппингов полей
        url_patterns: Паттерны URL для автоопределения
        content_check: Селектор, подтверждающий тип страницы
        pagination_selector: Селектор пагинации
        item_selector: Селектор одного item в списке
    """
    niche: NicheType
    name: str
    description: str = ""
    fields: list[FieldMapping] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)
    content_check: str | None = None
    pagination_selector: str | None = None
    item_selector: str | None = None

    def get_required_fields(self) -> list[FieldMapping]:
        return [f for f in self.fields if f.required]

    def get_field_names(self) -> list[str]:
        return [f.name for f in self.fields]


# ─── Predefined Schemas ──────────────────────────────────────────────────────

ECOMMERCE_SCHEMA = NicheSchema(
    niche=NicheType.ECOMMERCE,
    name="E-Commerce",
    description="Парсинг товаров: цена, описание, отзывы, рейтинг",
    url_patterns=[r"/product/", r"/item/", r"/dp/", r"/p/\d+", r"/goods/"],
    content_check="[data-product], .product-page, #product-detail, .product-info",
    pagination_selector=".pagination a, .pager a, [class*='pagination'] a",
    item_selector=".product-card, .product-item, [data-product-id], .search-item",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".product-title", "[data-product-name]", ".item-title h1", "h1.product-name"],
            required=True,
            description="Название товара",
        ),
        FieldMapping(
            name="price",
            selectors=[".price", "[data-price]", ".product-price", ".current-price", "meta[property='product:price:amount']"],
            attribute=None,
            regex=r"[\d\s,.]+",
            transform="float",
            required=True,
            description="Цена товара",
        ),
        FieldMapping(
            name="currency",
            selectors=["meta[property='product:price:currency']", ".currency"],
            attribute="content",
            transform="strip",
            default="USD",
            description="Валюты",
        ),
        FieldMapping(
            name="old_price",
            selectors=[".old-price", ".was-price", ".list-price", "[data-old-price]"],
            regex=r"[\d\s,.]+",
            transform="float",
            description="Старая цена (до скидки)",
        ),
        FieldMapping(
            name="description",
            selectors=[".description", "#description", ".product-description", "[data-description]", "meta[name='description']"],
            attribute=None,
            transform="strip",
            description="Описание товара",
        ),
        FieldMapping(
            name="rating",
            selectors=[".rating", "[data-rating]", ".star-rating", "meta[property='product:rating:value']"],
            regex=r"[\d.]+",
            transform="float",
            description="Рейтинг",
        ),
        FieldMapping(
            name="reviews_count",
            selectors=[".reviews-count", "[data-reviews-count]", ".review-count"],
            regex=r"\d+",
            transform="int",
            description="Количество отзывов",
        ),
        FieldMapping(
            name="brand",
            selectors=[".brand", "[data-brand]", "meta[property='product:brand']"],
            attribute=None,
            transform="strip",
            description="Бренд",
        ),
        FieldMapping(
            name="sku",
            selectors=["[data-sku]", ".sku", "meta[property='product:sku']"],
            attribute=None,
            transform="strip",
            description="Артикул/SKU",
        ),
        FieldMapping(
            name="availability",
            selectors=["[data-stock]", ".availability", ".stock-status", "meta[property='product:availability']"],
            attribute=None,
            transform="strip",
            description="Наличие",
        ),
        FieldMapping(
            name="images",
            selectors=["img.product-image", ".gallery-image", "[data-main-image]"],
            attribute="src",
            is_list=True,
            description="Изображения товара",
        ),
        FieldMapping(
            name="categories",
            selectors=[".breadcrumb a", ".category-breadcrumb a", "[data-category]"],
            is_list=True,
            transform="strip",
            description="Категории",
        ),
    ],
)


NEWS_SCHEMA = NicheSchema(
    niche=NicheType.NEWS,
    name="News",
    description="Парсинг новостных статей: заголовок, автор, дата, текст",
    url_patterns=[r"/news/", r"/article/", r"/blog/", r"/\d{4}/\d{2}/\d{2}/"],
    content_check="article, .article-body, .post-content, [itemprop='articleBody']",
    pagination_selector=".pagination a, .nav-links a, .page-numbers a",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".article-title", ".post-title", "meta[property='og:title']", "[itemprop='headline']"],
            attribute=None,
            transform="strip",
            required=True,
            description="Заголовок статьи",
        ),
        FieldMapping(
            name="content",
            selectors=["article", ".article-body", ".post-content", "[itemprop='articleBody']", ".entry-content"],
            attribute=None,
            transform="strip",
            required=True,
            description="Текст статьи",
        ),
        FieldMapping(
            name="author",
            selectors=[".author-name", ".byline", "[itemprop='author']", "meta[property='article:author']", "meta[name='author']"],
            attribute=None,
            transform="strip",
            description="Автор",
        ),
        FieldMapping(
            name="published_date",
            selectors=["time[datetime]", "meta[property='article:published_time']", ".publish-date", "[itemprop='datePublished']"],
            attribute="datetime",
            transform="strip",
            description="Дата публикации",
        ),
        FieldMapping(
            name="modified_date",
            selectors=["meta[property='article:modified_time']", ".updated-date", "[itemprop='dateModified']"],
            attribute="content",
            description="Дата обновления",
        ),
        FieldMapping(
            name="tags",
            selectors=["[rel='tag']", ".tags a", ".article-tags a", "meta[property='article:tag']"],
            is_list=True,
            transform="strip",
            description="Теги",
        ),
        FieldMapping(
            name="category",
            selectors=[".category", ".article-category", "meta[property='article:section']", ".breadcrumb a:last-child"],
            attribute=None,
            transform="strip",
            description="Категория",
        ),
        FieldMapping(
            name="summary",
            selectors=["meta[name='description']", "meta[property='og:description']", ".article-summary", ".excerpt"],
            attribute="content",
            transform="strip",
            description="Краткое описание",
        ),
        FieldMapping(
            name="image",
            selectors=["meta[property='og:image']", ".article-image img", "figure.main-image img", "[itemprop='image']"],
            attribute="content",
            description="Главное изображение",
        ),
    ],
)


REALTY_SCHEMA = NicheSchema(
    niche=NicheType.REALTY,
    name="Realty",
    description="Парсинг объявлений недвижимости: цена, площадь, адрес",
    url_patterns=[r"/realty/", r"/property/", r"/kvartira/", r"/flat/", r"/house/"],
    content_check="[data-property], .listing-detail, .property-page",
    pagination_selector=".pagination a",  # , .pager a
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".listing-title", ".property-title", "[data-property-title]"],
            required=True,
            description="Заголовок объявления",
        ),
        FieldMapping(
            name="price",
            selectors=[".price", "[data-price]", ".listing-price", ".property-price"],
            regex=r"[\d\s,.]+",
            transform="float",
            required=True,
            description="Цена",
        ),
        FieldMapping(
            name="address",
            selectors=[".address", "[data-address]", ".location", "[itemprop='address']"],
            transform="strip",
            description="Адрес",
        ),
        FieldMapping(
            name="area",
            selectors=[".area", "[data-area]", ".square", "[itemprop='floorSize']"],
            regex=r"[\d.]+",
            transform="float",
            description="Площадь (м²)",
        ),
        FieldMapping(
            name="rooms",
            selectors=[".rooms", "[data-rooms]", ".room-count"],
            regex=r"\d+",
            transform="int",
            description="Количество комнат",
        ),
        FieldMapping(
            name="floor",
            selectors=[".floor", "[data-floor]"],
            transform="strip",
            description="Этаж",
        ),
        FieldMapping(
            name="description",
            selectors=[".description", ".listing-description", ".property-description", "[itemprop='description']"],
            transform="strip",
            description="Описание",
        ),
        FieldMapping(
            name="seller",
            selectors=[".seller-name", ".agent-name", "[data-seller]", ".contact-name"],
            transform="strip",
            description="Продавец/Агент",
        ),
        FieldMapping(
            name="images",
            selectors=[".gallery img", ".property-images img", "[data-image]"],
            attribute="src",
            is_list=True,
            description="Изображения",
        ),
    ],
)


MEDTECH_SCHEMA = NicheSchema(
    niche=NicheType.MEDTECH,
    name="MedTech",
    description="Парсинг медицинских данных: препараты, клиники, статьи",
    url_patterns=[r"/medicine/", r"/drug/", r"/clinic/", r"/doctor/", r"/health/", r"/med/"],
    content_check="article, .medical-content, .drug-info, .clinic-page",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".drug-name", ".clinic-name", ".article-title"],
            required=True,
            description="Название",
        ),
        FieldMapping(
            name="description",
            selectors=[".description", ".drug-description", ".clinic-about", "article .content"],
            transform="strip",
            description="Описание",
        ),
        FieldMapping(
            name="indications",
            selectors=[".indications", "[data-indications]", ".usage"],
            transform="strip",
            description="Показания к применению",
        ),
        FieldMapping(
            name="contraindications",
            selectors=[".contraindications", "[data-contraindications]", ".cautions"],
            transform="strip",
            description="Противопоказания",
        ),
        FieldMapping(
            name="side_effects",
            selectors=[".side-effects", "[data-side-effects]", ".adverse-effects"],
            transform="strip",
            description="Побочные эффекты",
        ),
        FieldMapping(
            name="dosage",
            selectors=[".dosage", "[data-dosage]", ".directions"],
            transform="strip",
            description="Дозировка/Способ применения",
        ),
        FieldMapping(
            name="composition",
            selectors=[".composition", "[data-composition]", ".ingredients"],
            transform="strip",
            description="Состав",
        ),
        FieldMapping(
            name="price",
            selectors=[".price", "[data-price]"],
            regex=r"[\d\s,.]+",
            transform="float",
            description="Цена",
        ),
        FieldMapping(
            name="manufacturer",
            selectors=[".manufacturer", "[data-manufacturer]", ".brand"],
            transform="strip",
            description="Производитель",
        ),
    ],
)


JOBS_SCHEMA = NicheSchema(
    niche=NicheType.JOBS,
    name="Jobs",
    description="Парсинг вакансий: должность, зарплата, компания, требования",
    url_patterns=[r"/job/", r"/vacancy/", r"/career/", r"/vakansiya/", r"/rabota/"],
    content_check=".job-detail, .vacancy-page, [data-vacancy]",
    pagination_selector=".pagination a",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".job-title", ".vacancy-title", "[data-job-title]"],
            required=True,
            description="Должность",
        ),
        FieldMapping(
            name="company",
            selectors=[".company-name", ".employer", "[data-company]", ".organization"],
            transform="strip",
            required=True,
            description="Компания",
        ),
        FieldMapping(
            name="salary",
            selectors=[".salary", "[data-salary]", ".compensation", ".wage"],
            regex=r"[\d\s,.]+",
            transform="strip",
            description="Зарплата",
        ),
        FieldMapping(
            name="location",
            selectors=[".location", "[data-location]", ".city", ".address"],
            transform="strip",
            description="Локация",
        ),
        FieldMapping(
            name="experience",
            selectors=[".experience", "[data-experience]", ".exp-required"],
            transform="strip",
            description="Требуемый опыт",
        ),
        FieldMapping(
            name="description",
            selectors=[".job-description", ".vacancy-description", "[data-description]"],
            transform="strip",
            description="Описание вакансии",
        ),
        FieldMapping(
            name="requirements",
            selectors=[".requirements", ".must-have", ".skills", ".qualifications"],
            transform="strip",
            description="Требования",
        ),
        FieldMapping(
            name="employment_type",
            selectors=[".employment-type", "[data-employment]", ".work-type"],
            transform="strip",
            description="Тип занятости",
        ),
    ],
)


AUTO_SCHEMA = NicheSchema(
    niche=NicheType.AUTO,
    name="Auto",
    description="Парсинг объявлений авто: марка, модель, цена, год, пробег",
    url_patterns=[r"/auto/", r"/car/", r"/avto/", r"/vehicle/", r"/drom", r"/avito/"],
    content_check=".car-detail, .auto-page, [data-vehicle], .listing-detail",
    pagination_selector=".pagination a",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".car-title", ".auto-title", "[data-title]"],
            required=True,
            description="Заголовок",
        ),
        FieldMapping(
            name="price",
            selectors=[".price", "[data-price]", ".car-price"],
            regex=r"[\d\s,.]+",
            transform="float",
            required=True,
            description="Цена",
        ),
        FieldMapping(
            name="brand",
            selectors=[".brand", "[data-brand]", ".make"],
            transform="strip",
            description="Марка",
        ),
        FieldMapping(
            name="model",
            selectors=[".model", "[data-model]"],
            transform="strip",
            description="Модель",
        ),
        FieldMapping(
            name="year",
            selectors=[".year", "[data-year]", ".year-manufactured"],
            regex=r"\d{4}",
            transform="int",
            description="Год выпуска",
        ),
        FieldMapping(
            name="mileage",
            selectors=[".mileage", "[data-mileage]", ".probeg", ".km"],
            regex=r"[\d\s,.]+",
            transform="float",
            description="Пробег",
        ),
        FieldMapping(
            name="engine",
            selectors=[".engine", "[data-engine]", ".engine-volume"],
            transform="strip",
            description="Двигатель",
        ),
        FieldMapping(
            name="transmission",
            selectors=[".transmission", "[data-transmission]", ".trans-type"],
            transform="strip",
            description="Коробка передач",
        ),
        FieldMapping(
            name="drive",
            selectors=[".drive", "[data-drive]", ".drivetrain", ".wd"],
            transform="strip",
            description="Привод",
        ),
        FieldMapping(
            name="description",
            selectors=[".description", ".car-description", ".auto-description"],
            transform="strip",
            description="Описание",
        ),
        FieldMapping(
            name="images",
            selectors=[".gallery img", ".car-images img", "[data-image]"],
            attribute="src",
            is_list=True,
            description="Изображения",
        ),
    ],
)


# ─── Social / Content Platform Schemas ───────────────────────────────────────

HABR_SCHEMA = NicheSchema(
    niche=NicheType.HABR,
    name="Habr",
    description="Парсинг статей Хабра: заголовок, автор, рейтинг, текст, хабы",
    url_patterns=[r"habr\.com/", r"habr\.ru/"],
    content_check="article, .post__body, .tm-article-body",
    pagination_selector=".tm-pagination__pages a, .pagination__pages a",
    item_selector=".tm-articles-list__item, article.tm-articles-list__item",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".tm-article-snippet__title", ".post__title", "meta[property='og:title']"],
            attribute=None,
            transform="strip",
            required=True,
            description="Заголовок статьи",
        ),
        FieldMapping(
            name="content",
            selectors=[".tm-article-body", ".post__body", "#post-content-body", "article .article__body"],
            attribute=None,
            transform="strip",
            required=True,
            description="Текст статьи",
        ),
        FieldMapping(
            name="author",
            selectors=[".tm-user-info__username", ".post__meta .user-info__nickname", "a[data-test-id='author-info']", ".tm-article-snippet__author"],
            attribute=None,
            transform="strip",
            description="Автор статьи",
        ),
        FieldMapping(
            name="author_url",
            selectors=[".tm-user-info__username", "a[href*='/users/']"],
            attribute="href",
            description="Ссылка на профиль автора",
        ),
        FieldMapping(
            name="rating",
            selectors=[".tm-votes-lever__score", ".post__total_voting", "[data-test-id='votes-meter-value']", ".tm-article-rating__value"],
            regex=r"-?\d+",
            transform="int",
            description="Рейтинг статьи",
        ),
        FieldMapping(
            name="views",
            selectors=[".tm-icon-counter__value", ".post__views-count", "[data-test-id='article-stats']"],
            regex=r"[\d\s]+",
            transform="int",
            description="Количество просмотров",
        ),
        FieldMapping(
            name="comments_count",
            selectors=[".tm-article-comments-counter-link__value", ".post__comments-count", "[data-test-id='comments-count']"],
            regex=r"\d+",
            transform="int",
            description="Количество комментариев",
        ),
        FieldMapping(
            name="published_date",
            selectors=["time[datetime]", ".tm-article-snippet__datetime", ".post__time", "meta[property='article:published_time']"],
            attribute="datetime",
            transform="strip",
            description="Дата публикации",
        ),
        FieldMapping(
            name="hubs",
            selectors=[".tm-hubs-list__hub-link", ".post__hubs a", ".tm-article-snippet__hubs a", "a[href*='/hub/']"],
            is_list=True,
            transform="strip",
            description="Хабы (теги тематик)",
        ),
        FieldMapping(
            name="tags",
            selectors=[".tm-tags-list__tag", ".post__tags a", ".tm-article-snippet__tags a"],
            is_list=True,
            transform="strip",
            description="Теги статьи",
        ),
        FieldMapping(
            name="reading_time",
            selectors=[".tm-article-reading-time__label", ".post__reading-time"],
            regex=r"\d+",
            transform="int",
            description="Время чтения (мин)",
        ),
        FieldMapping(
            name="bookmarks_count",
            selectors=[".tm-article-snippet__favorites-count", ".post__bookmarks-count"],
            regex=r"\d+",
            transform="int",
            description="Количество закладок",
        ),
    ],
)


VCRU_SCHEMA = NicheSchema(
    niche=NicheType.VCRU,
    name="VC.ru",
    description="Парсинг статей VC.ru: заголовок, автор, текст, рейтинг",
    url_patterns=[r"vc\.ru/"],
    content_check=".content--detail, .article-content, .l-page",
    pagination_selector=".pagination a, .pager a",
    item_selector=".content-feed__item, .feed__item, article.b-article",
    fields=[
        FieldMapping(
            name="title",
            selectors=["h1", ".content-title", ".b-article__title", "meta[property='og:title']"],
            attribute=None,
            transform="strip",
            required=True,
            description="Заголовок статьи",
        ),
        FieldMapping(
            name="content",
            selectors=[".content--detail .content", ".b-article__text", ".article__body", ".l-content .content"],
            attribute=None,
            transform="strip",
            required=True,
            description="Текст статьи",
        ),
        FieldMapping(
            name="author",
            selectors=[".content-author__name", ".b-article__author-name", ".user-info__name", "a[href*='/user/']"],
            attribute=None,
            transform="strip",
            description="Автор статьи",
        ),
        FieldMapping(
            name="author_url",
            selectors=[".content-author a", ".b-article__author a"],
            attribute="href",
            description="Ссылка на профиль автора",
        ),
        FieldMapping(
            name="rating",
            selectors=[".content-vote__result", ".b-article__vote-value", ".vote__value"],
            regex=r"-?\d+",
            transform="int",
            description="Рейтинг статьи",
        ),
        FieldMapping(
            name="views",
            selectors=[".content-views__count", ".b-article__views", ".stats__views"],
            regex=r"[\d\s]+",
            transform="int",
            description="Количество просмотров",
        ),
        FieldMapping(
            name="comments_count",
            selectors=[".content-comments__count", ".b-article__comments-count"],
            regex=r"\d+",
            transform="int",
            description="Количество комментариев",
        ),
        FieldMapping(
            name="published_date",
            selectors=["time[datetime]", ".content-time", ".b-article__date", "meta[property='article:published_time']"],
            attribute="datetime",
            transform="strip",
            description="Дата публикации",
        ),
        FieldMapping(
            name="tags",
            selectors=[".content-tags a", ".b-article__tags a", ".tags__item", "a[href*='/tag/']"],
            is_list=True,
            transform="strip",
            description="Теги статьи",
        ),
        FieldMapping(
            name="category",
            selectors=[".content-category", ".b-article__category", ".breadcrumbs a:last-child"],
            transform="strip",
            description="Категория",
        ),
        FieldMapping(
            name="image",
            selectors=["meta[property='og:image']", ".content-image img", ".b-article__image img"],
            attribute="content",
            description="Главное изображение",
        ),
    ],
)


TWITTER_SCHEMA = NicheSchema(
    niche=NicheType.TWITTER,
    name="Twitter/X",
    description="Парсинг твитов: автор, текст, лайки, ретвиты, дата",
    url_patterns=[r"twitter\.com/", r"x\.com/", r"t\.co/"],
    content_check="[data-testid='tweet'], article, .tweet",
    pagination_selector=None,  # infinite scroll
    item_selector="[data-testid='tweet'], article[role='article']",
    fields=[
        FieldMapping(
            name="author",
            selectors=["[data-testid='User-Name']", ".tweet-user .fullname", "a[role='link'] div span"],
            attribute=None,
            transform="strip",
            required=True,
            description="Автор твита",
        ),
        FieldMapping(
            name="author_handle",
            selectors=["[data-testid='User-Name'] a[role='link']", ".tweet-user .username"],
            regex=r"@[\w]+",
            transform="strip",
            description="@username автора",
        ),
        FieldMapping(
            name="text",
            selectors=["[data-testid='tweetText']", ".tweet-text", "[lang]"],
            attribute=None,
            transform="strip",
            required=True,
            description="Текст твита",
        ),
        FieldMapping(
            name="likes",
            selectors=["[data-testid='like']", "[data-testid='unlike']", ".tweet-stats .favorite-count"],
            regex=r"[\d,.]+[KkMm]?",
            transform="strip",
            description="Количество лайков",
        ),
        FieldMapping(
            name="retweets",
            selectors=["[data-testid='retweet']", "[data-testid='unretweet']", ".tweet-stats .retweet-count"],
            regex=r"[\d,.]+[KkMm]?",
            transform="strip",
            description="Количество ретвитов",
        ),
        FieldMapping(
            name="replies",
            selectors=["[data-testid='reply']", ".tweet-stats .reply-count"],
            regex=r"[\d,.]+[KkMm]?",
            transform="strip",
            description="Количество ответов",
        ),
        FieldMapping(
            name="views",
            selectors=["[data-testid='app-text-transition-container'] span", ".tweet-stats .view-count"],
            regex=r"[\d,.]+[KkMmBb]?",
            transform="strip",
            description="Количество просмотров",
        ),
        FieldMapping(
            name="published_date",
            selectors=["time[datetime]", ".tweet-timestamp time", "a[href*='/status/'] time"],
            attribute="datetime",
            transform="strip",
            description="Дата публикации",
        ),
        FieldMapping(
            name="tweet_url",
            selectors=["time", "a[href*='/status/']"],
            attribute="href",
            description="URL твита",
        ),
        FieldMapping(
            name="hashtags",
            selectors=["a[href*='/hashtag/']", "a[href*='?q=%23']"],
            is_list=True,
            transform="strip",
            description="Хэштеги",
        ),
        FieldMapping(
            name="mentions",
            selectors=["a[href*='/search?q=%40']", "a[role='link'] span"],
            regex=r"@[\w]+",
            is_list=True,
            transform="strip",
            description="Упоминания (@username)",
        ),
        FieldMapping(
            name="images",
            selectors=["[data-testid='tweetPhoto'] img", ".tweet-media img", "img[alt='Image']"],
            attribute="src",
            is_list=True,
            description="Изображения в твите",
        ),
    ],
)


TELEGRAM_SCHEMA = NicheSchema(
    niche=NicheType.TELEGRAM,
    name="Telegram",
    description="Парсинг постов Telegram-каналов: текст, дата, просмотры, реакции",
    url_patterns=[r"t\.me/", r"telegram\.me/", r"telegram\.org/"],
    content_check=".tgme_channel_post, .tgme_widget_message, .im_message_wrap",
    pagination_selector=None,  # infinite scroll / load more
    item_selector=".tgme_channel_post, .tgme_widget_message, .im_message_wrap",
    fields=[
        FieldMapping(
            name="channel_name",
            selectors=[".tgme_channel_info_header_title", ".tgme_header_link", ".im_dialog_peer"],
            attribute=None,
            transform="strip",
            required=True,
            description="Название канала",
        ),
        FieldMapping(
            name="channel_url",
            selectors=[".tgme_header_link", ".tgme_channel_info_header a"],
            attribute="href",
            description="URL канала",
        ),
        FieldMapping(
            name="text",
            selectors=[".tgme_channel_post_text", ".tgme_widget_message_text", ".im_message_text"],
            attribute=None,
            transform="strip",
            required=True,
            description="Текст поста",
        ),
        FieldMapping(
            name="views",
            selectors=[".tgme_widget_message_views", ".tgme_channel_post_views", ".im_message_views"],
            regex=r"[\d\s,.]+[KkMm]?",
            transform="strip",
            description="Количество просмотров",
        ),
        FieldMapping(
            name="published_date",
            selectors=[".tgme_widget_message_date time", ".tgme_channel_post_date time", "time[datetime]"],
            attribute="datetime",
            transform="strip",
            description="Дата публикации",
        ),
        FieldMapping(
            name="post_url",
            selectors=[".tgme_widget_message_date", ".tgme_channel_post_date", "a[href*='/s/']"],
            attribute="href",
            description="URL поста",
        ),
        FieldMapping(
            name="reactions",
            selectors=[".tgme_widget_message_reactions", ".tgme_channel_post_reactions", ".im_message_reactions"],
            is_list=True,
            transform="strip",
            description="Реакции (emoji + количество)",
        ),
        FieldMapping(
            name="images",
            selectors=[".tgme_widget_message_photo_wrap", ".tgme_channel_post_photo", ".im_message_photo img"],
            attribute="href",
            is_list=True,
            description="Изображения в посте",
        ),
        FieldMapping(
            name="video",
            selectors=[".tgme_widget_message_video_wrap", ".tgme_channel_post_video", "video source"],
            attribute="src",
            description="Видео в посте",
        ),
        FieldMapping(
            name="forwarded_from",
            selectors=[".tgme_widget_message_forwarded_from", ".im_message_fwd_from"],
            transform="strip",
            description="Переслано от",
        ),
        FieldMapping(
            name="reply_to",
            selectors=[".tgme_widget_message_reply", ".im_message_reply"],
            transform="strip",
            description="Ответ на пост",
        ),
    ],
)


# Registry of all predefined schemas
SCHEMA_REGISTRY: dict[NicheType, NicheSchema] = {
    NicheType.ECOMMERCE: ECOMMERCE_SCHEMA,
    NicheType.NEWS: NEWS_SCHEMA,
    NicheType.REALTY: REALTY_SCHEMA,
    NicheType.MEDTECH: MEDTECH_SCHEMA,
    NicheType.JOBS: JOBS_SCHEMA,
    NicheType.AUTO: AUTO_SCHEMA,
    NicheType.HABR: HABR_SCHEMA,
    NicheType.VCRU: VCRU_SCHEMA,
    NicheType.TWITTER: TWITTER_SCHEMA,
    NicheType.TELEGRAM: TELEGRAM_SCHEMA,
}

# Aliases
NicheProfile = NicheType


def get_schema(niche: NicheType) -> NicheSchema:
    """Получить схему по типу ниши."""
    if niche not in SCHEMA_REGISTRY:
        raise ValueError(
            f"Unknown niche: {niche}. Available: {list(SCHEMA_REGISTRY.keys())}"
        )
    return SCHEMA_REGISTRY[niche]


def detect_niche(url: str) -> NicheType:
    """Автоматически определить нишу по URL."""
    for niche_type, schema in SCHEMA_REGISTRY.items():
        for pattern in schema.url_patterns:
            if re.search(pattern, url):
                return niche_type
    return NicheType.GENERIC


# ─── Transforms ──────────────────────────────────────────────────────────────

TRANSFORMS = {
    "int": lambda v: int(re.sub(r"[^\d-]", "", str(v))) if v else None,
    "float": lambda v: float(re.sub(r"[^\d.,-]", "", str(v)).replace(",", ".")) if v else None,
    "strip": lambda v: str(v).strip() if v else None,
    "lowercase": lambda v: str(v).lower() if v else None,
    "uppercase": lambda v: str(v).upper() if v else None,
}


# ─── Parse Result ────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    """Результат парсинга страницы по схеме.

    Attributes:
        url: URL страницы
        niche: Тип ниши
        data: Извлечённые данные
        confidence: Уверенность (0-1) на основе заполненности полей
        parse_time_ms: Время парсинга в мс
        page_title: Заголовок страницы
        domain: Домен
        errors: Ошибки парсинга
        content_hash: Хэш контента
        parsed_at: Время парсинга
    """
    url: str
    niche: NicheType
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    parse_time_ms: float = 0.0
    page_title: str = ""
    domain: str = ""
    errors: list[str] = field(default_factory=list)
    content_hash: str = ""
    parsed_at: str = ""

    @property
    def is_valid(self) -> bool:
        """Результат валиден (все обязательные поля заполнены)."""
        return self.confidence > 0.3 and not any(
            k in self.errors for k in ("page_load_failed", "selector_not_found")
        )

    @property
    def domain_parsed(self) -> str:
        return self.domain or urlparse(self.url).netloc

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "niche": self.niche.value,
            "data": self.data,
            "confidence": self.confidence,
            "parse_time_ms": self.parse_time_ms,
            "page_title": self.page_title,
            "domain": self.domain,
            "errors": self.errors,
            "content_hash": self.content_hash,
            "parsed_at": self.parsed_at,
        }

    def summary(self) -> str:
        filled = sum(1 for v in self.data.values() if v is not None)
        total = len(self.data)
        return (
            f"ParseResult({self.niche.value}): {filled}/{total} fields | "
            f"confidence={self.confidence:.1%} | "
            f"{self.parse_time_ms:.0f}ms | {self.domain_parsed}"
        )


# ─── DataParser ──────────────────────────────────────────────────────────────

class DataParser:
    """Универсальный адаптер парсинга данных под разные ниши.

    Расширяет PageParser добавляя:
    - Декларативные схемы для разных ниш
    - Автоопределение типа контента по URL
    - Пост-обработку и нормализацию
    - Вычисление уверенности (confidence score)

    Использование:
        >>> # Автоопределение ниши
        >>> parser = DataParser(browser_manager)
        >>> result = await parser.parse("https://shop.example.com/product/123")
        >>> # result.niche == NicheType.ECOMMERCE
        >>> # result.data == {"title": "...", "price": 99.99, ...}

        >>> # Явное указание ниши
        >>> parser = DataParser(browser_manager, niche=NicheType.NEWS)
        >>> result = await parser.parse("https://news.example.com/article")

        >>> # Кастомная схема
        >>> schema = NicheSchema(
        ...     niche=NicheType.CUSTOM,
        ...     name="My Parser",
        ...     fields=[
        ...         FieldMapping(name="custom_field", selectors=[".my-class"]),
        ...     ],
        ... )
        >>> parser = DataParser(browser_manager, custom_schema=schema)
    """

    def __init__(
        self,
        browser_manager: Any,
        niche: NicheType | None = None,
        custom_schema: NicheSchema | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        strict: bool = False,
    ):
        """
        Args:
            browser_manager: Экземпляр BrowserManager
            niche: Ниша (None = автоопределение)
            custom_schema: Кастомная схема (переопределяет niche)
            timeout: Таймаут загрузки страницы
            max_retries: Макс. повторных попыток
            strict: Строгий режим (fail если обязательные поля не найдены)
        """
        from .browser import BrowserManager
        self._browser_mgr: BrowserManager = browser_manager
        self._niche = niche
        self._custom_schema = custom_schema
        self._timeout = timeout
        self._max_retries = max_retries
        self._strict = strict
        self._page: Page | None = None
        self._base_parser: PageParser | None = None

    async def _ensure_page(self, url: str) -> Page:
        """Получить или создать страницу и перейти по URL."""
        try:
            if self._page is not None:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=int(self._timeout * 1000))
                return self._page
        except Exception:
            # Страница мертва — создадим новую
            self._page = None

        context = await self._browser_mgr.get_context()
        self._page = await context.new_page()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=int(self._timeout * 1000))
        return self._page

    async def parse(
        self,
        url: str,
        niche: NicheType | None = None,
        custom_schema: NicheSchema | None = None,
    ) -> ParseResult:
        """Спарсить страницу и извлечь данные по схеме.

        Args:
            url: URL страницы
            niche: Переопределение ниши (None = из конструктора или авто)
            custom_schema: Переопределение схемы

        Returns:
            ParseResult с извлечёнными данными
        """
        start = time.monotonic()
        niche_type = niche or self._niche or detect_niche(url)
        schema = custom_schema or self._custom_schema or get_schema(niche_type)

        result = ParseResult(
            url=url,
            niche=niche_type,
            domain=urlparse(url).netloc,
            parsed_at=datetime.now(timezone.utc).isoformat(),
        )

        for attempt in range(self._max_retries):
            try:
                page = await self._ensure_page(url)
                self._base_parser = PageParser(page)

                # Проверить content_check селектор (если есть)
                if schema.content_check:
                    try:
                        await page.wait_for_selector(
                            schema.content_check,
                            timeout=5000,
                            state="attached",
                        )
                    except Exception:
                        if attempt < self._max_retries - 1:
                            logger.debug(f"Content check failed, retry {attempt + 1}")
                            continue

                # Извлечь данные по схеме
                data, errors = await self._extract_by_schema(page, schema)
                result.data = data
                result.errors = errors
                result.page_title = await page.title()

                # Content hash
                text_content = await page.evaluate("() => document.body.innerText")
                result.content_hash = hashlib.md5(text_content.encode()).hexdigest()

                # Confidence
                result.confidence = self._compute_confidence(schema, data)

                break

            except Exception as e:
                err_msg = f"Parse error (attempt {attempt + 1}): {e}"
                logger.warning(err_msg)
                result.errors.append(str(e))
                if attempt == self._max_retries - 1:
                    result.errors.append("page_load_failed")
                self._page = None  # пересоздать страницу

        result.parse_time_ms = (time.monotonic() - start) * 1000

        if self._strict and result.errors:
            logger.error(f"Strict mode: parse failed for {url}: {result.errors}")
        else:
            logger.info(result.summary())

        return result

    async def parse_list(
        self,
        url: str,
        item_selector: str | None = None,
        max_items: int = 50,
        niche: NicheType | None = None,
    ) -> list[ParseResult]:
        """Спарсить страницу со списком (результаты поиска, каталог).

        Для каждого элемента списка выстраивает минимальные данные.
        Для полного парсинга — нужно открыть каждую ссылку отдельно.

        Args:
            url: URL страницы со списком
            item_selector: CSS-селектор одного элемента (None = из схемы)
            max_items: Макс. количество элементов
            niche: Тип ниши

        Returns:
            Список ParseResult для каждого элемента (ссылка + базовые данные)
        """
        niche_type = niche or self._niche or detect_niche(url)
        schema = self._custom_schema or get_schema(niche_type)

        item_sel = item_selector or schema.item_selector or ".item"
        results: list[ParseResult] = []

        try:
            page = await self._ensure_page(url)
            items = await page.query_selector_all(item_sel)
            items = items[:max_items]

            for item_el in items:
                # Извлечь ссылку и базовые данные из превью
                link_el = await item_el.query_selector("a[href]")
                href = await link_el.get_attribute("href") if link_el else None
                if not href:
                    continue

                full_url = href if href.startswith("http") else f"{urlparse(url).scheme}://{urlparse(url).netloc}{href}"

                # Попробовать извлечь title и price из превью
                data: dict[str, Any] = {}
                for field in schema.fields[:3]:  # первые 3 поля для превью
                    for sel in field.selectors[:2]:
                        try:
                            el = await item_el.query_selector(sel)
                            if el:
                                if field.attribute:
                                    val = await el.get_attribute(field.attribute)
                                else:
                                    val = await el.inner_text()
                                if val:
                                    data[field.name] = val.strip()
                                    break
                        except Exception:
                            continue

                data["_list_url"] = url
                data["_list_index"] = len(results)

                results.append(ParseResult(
                    url=full_url,
                    niche=niche_type,
                    data=data,
                    confidence=0.2,  # низкая уверенность для превью
                    domain=urlparse(full_url).netloc,
                    parsed_at=datetime.now(timezone.utc).isoformat(),
                ))

        except Exception as e:
            logger.error(f"parse_list error: {e}")

        logger.info(f"parse_list: extracted {len(results)} items from {url}")
        return results

    async def _extract_by_schema(
        self,
        page: Page,
        schema: NicheSchema,
    ) -> tuple[dict[str, Any], list[str]]:
        """Извлечь данные из страницы по схеме.

        Returns:
            Tuple of (data_dict, errors_list)
        """
        data: dict[str, Any] = {}
        errors: list[str] = []

        for field_def in schema.fields:
            value: Any = None
            found = False

            for selector in field_def.selectors:
                try:
                    locator = page.locator(selector)
                    count = await locator.count()

                    if count == 0:
                        continue

                    if field_def.is_list:
                        # Извлечь все совпадения
                        items: list[str] = []
                        for i in range(count):
                            if field_def.attribute:
                                val = await locator.nth(i).get_attribute(field_def.attribute)
                            else:
                                val = await locator.nth(i).inner_text()
                            if val:
                                items.append(val.strip())
                        if items:
                            value = items
                            found = True
                            break
                    else:
                        # Первое совпадение
                        if field_def.attribute:
                            val = await locator.first.get_attribute(field_def.attribute)
                        else:
                            val = await locator.first.inner_text()

                        if val:
                            value = val.strip()
                            found = True
                            break

                except Exception as e:
                    logger.debug(f"Selector '{selector}' for '{field_def.name}' failed: {e}")
                    continue

            # Если не найдено — использовать по умолчанию
            if not found:
                value = field_def.default
                if field_def.required and value is None:
                    errors.append(f"required_field_missing:{field_def.name}")

            # Применить regex если указан
            if value is not None and field_def.regex:
                if field_def.is_list:
                    value = [
                        m.group() if (m := re.search(field_def.regex, str(v))) else v
                        for v in value
                    ]
                else:
                    m = re.search(field_def.regex, str(value))
                    if m:
                        value = m.group()

            # Применить transform если указан
            if value is not None and field_def.transform:
                try:
                    transform_fn = TRANSFORMS.get(field_def.transform)
                    if transform_fn:
                        if field_def.is_list:
                            value = [transform_fn(v) for v in value]
                        else:
                            value = transform_fn(value)
                except (ValueError, TypeError) as e:
                    logger.debug(f"Transform '{field_def.transform}' failed for '{field_def.name}': {e}")
                    if field_def.default is not None:
                        value = field_def.default

            data[field_def.name] = value

        return data, errors

    def _compute_confidence(
        self,
        schema: NicheSchema,
        data: dict[str, Any],
    ) -> float:
        """Вычислить уверенность результата (0-1).

        На основе:
        - Заполненность обязательных полей (вес 60%)
        - Заполненность опциональных полей (вес 40%)
        """
        required = schema.get_required_fields()
        all_fields = schema.fields

        if not all_fields:
            return 0.0

        # Required fields score (60%)
        req_score = 0.0
        if required:
            req_filled = sum(1 for f in required if data.get(f.name) is not None)
            req_score = req_filled / len(required)

        # Optional fields score (40%)
        optional = [f for f in all_fields if f not in required]
        opt_score = 0.0
        if optional:
            opt_filled = sum(1 for f in optional if data.get(f.name) is not None)
            opt_score = opt_filled / len(optional)

        return req_score * 0.6 + opt_score * 0.4

    async def close(self) -> None:
        """Закрыть страницу."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None


# ─── Batch Parser ────────────────────────────────────────────────────────────

class BatchParser:
    """Пакетный парсер для обработки списка URL.

    Использует DataParser для параллельного парсинга
    с контролем скорости.

    Использование:
        >>> batch = BatchParser(browser_manager, niche=NicheType.NEWS)
        >>> results = await batch.parse_batch([
        ...     "https://news.example.com/1",
        ...     "https://news.example.com/2",
        ...     "https://news.example.com/3",
        ... ], max_concurrent=2)
    """

    def __init__(
        self,
        browser_manager: Any,
        niche: NicheType | None = None,
        custom_schema: NicheSchema | None = None,
        requests_per_second: float = 1.0,
        max_concurrent: int = 3,
    ):
        self._browser_mgr = browser_manager
        self._niche = niche
        self._custom_schema = custom_schema
        self._rps = requests_per_second
        self._max_concurrent = max_concurrent

    async def parse_batch(
        self,
        urls: list[str],
        niche: NicheType | None = None,
    ) -> list[ParseResult]:
        """Спарсить список URL.

        Args:
            urls: Список URL
            niche: Переопределение ниши

        Returns:
            Список ParseResult (включая ошибки)
        """
        import asyncio

        results: list[ParseResult] = []
        delay = 1.0 / self._rps if self._rps > 0 else 0
        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _parse_one(url: str) -> ParseResult:
            async with semaphore:
                parser = DataParser(
                    self._browser_mgr,
                    niche=niche or self._niche,
                    custom_schema=self._custom_schema,
                )
                try:
                    result = await parser.parse(url)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    return result
                finally:
                    await parser.close()

        tasks = [_parse_one(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обернуть исключения в ParseResult с ошибками
        final_results: list[ParseResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                niche_type = niche or self._niche or detect_niche(urls[i])
                final_results.append(ParseResult(
                    url=urls[i],
                    niche=niche_type,
                    errors=[str(r), "batch_parse_exception"],
                ))
            else:
                final_results.append(r)

        success = sum(1 for r in final_results if r.is_valid)
        logger.info(f"BatchParser: {success}/{len(final_results)} valid results from {len(urls)} URLs")
        return final_results


# ─── Export Utils ────────────────────────────────────────────────────────────

def export_to_csv(results: list[ParseResult], output_path: str) -> str:
    """Экспорт результатов в CSV."""
    if not results:
        return ""

    # Собрать все уникальные поля
    all_fields: list[str] = []
    field_set: set[str] = set()
    for r in results:
        for k in r.data.keys():
            if k not in field_set:
                all_fields.append(k)
                field_set.add(k)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "niche", "confidence", "domain"] + all_fields)
        for r in results:
            row = [
                r.url,
                r.niche.value,
                f"{r.confidence:.2f}",
                r.domain,
            ]
            for field in all_fields:
                val = r.data.get(field, "")
                if isinstance(val, list):
                    val = "; ".join(str(v) for v in val)
                row.append(str(val) if val is not None else "")
            writer.writerow(row)

    logger.info(f"CSV exported: {output_path} ({len(results)} rows)")
    return output_path


def export_to_json(results: list[ParseResult], output_path: str) -> str:
    """Экспорт результатов в JSON."""
    data = {
        "meta": {
            "total": len(results),
            "valid": sum(1 for r in results if r.is_valid),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "results": [r.to_dict() for r in results],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON exported: {output_path} ({len(results)} results)")
    return output_path
