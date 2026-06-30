"""
Scrapy Items — универсальные модели данных для парсинга.

Каждый Item — это структурированный контейнер для данных,
извлечённых из веб-страниц. Используются в Spider и Pipeline.

Playwright-интеграция: Spider может возвращать эти items
после обработки через PageParser или data_parser из основного кита.
"""

from __future__ import annotations

import scrapy


class ScrapedPage(scrapy.Item):
    """Универсальный item — одна спарсенная страница."""

    # Идентификация
    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    # Контент
    title = scrapy.Field()
    text = scrapy.Field()
    html = scrapy.Field()
    meta = scrapy.Field()  # dict: description, keywords, og:*

    # Структурированные данные
    json_ld = scrapy.Field()  # list: JSON-LD разметка
    opengraph = scrapy.Field()  # dict: OpenGraph теги

    # Навигация
    links = scrapy.Field()  # list[dict]: [{text, href}]
    images = scrapy.Field()  # list[str]: src

    # Извлечённые данные
    structured = scrapy.Field()  # dict: данные по схеме (DataParser)
    emails = scrapy.Field()  # list[str]
    phones = scrapy.Field()  # list[str]

    # Метаданные
    crawl_time = scrapy.Field()  # ISO timestamp
    depth = scrapy.Field()  # int: глубина обхода
    referer = scrapy.Field()  # str: откуда пришли

    # Технические
    status_code = scrapy.Field()
    content_type = scrapy.Field()
    encoding = scrapy.Field()


class ScrapedProduct(scrapy.Item):
    """Товар — e-commerce парсинг."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    # Основные данные
    title = scrapy.Field()
    price = scrapy.Field()  # float
    currency = scrapy.Field()  # str: RUB, USD, EUR
    old_price = scrapy.Field()  # float
    discount_percent = scrapy.Field()  # float

    # Описание
    description = scrapy.Field()
    brand = scrapy.Field()
    sku = scrapy.Field()
    barcode = scrapy.Field()

    # Медиа
    images = scrapy.Field()  # list[str]: URLs
    thumbnail = scrapy.Field()  # str: URL

    # Категоризация
    categories = scrapy.Field()  # list[str]
    tags = scrapy.Field()  # list[str]

    # Наличие
    availability = scrapy.Field()  # str: in_stock, out_of_stock, preorder
    stock_quantity = scrapy.Field()  # int

    # Отзывы
    rating = scrapy.Field()  # float
    reviews_count = scrapy.Field()  # int

    # Доставка
    delivery_price = scrapy.Field()
    delivery_time = scrapy.Field()

    crawl_time = scrapy.Field()


class ScrapedArticle(scrapy.Item):
    """Статья / новость / пост."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    # Контент
    title = scrapy.Field()
    content = scrapy.Field()  # Полный текст
    summary = scrapy.Field()  # Краткое описание

    # Авторство
    author = scrapy.Field()
    author_url = scrapy.Field()

    # Даты
    published_date = scrapy.Field()  # ISO 8601
    modified_date = scrapy.Field()  # ISO 8601

    # Категоризация
    tags = scrapy.Field()
    category = scrapy.Field()
    hubs = scrapy.Field()  # Хабы (для Хабра)

    # Метрики (если доступны)
    views_count = scrapy.Field()  # int
    comments_count = scrapy.Field()  # int
    rating = scrapy.Field()  # int/float
    bookmarks_count = scrapy.Field()  # int

    # Медиа
    image = scrapy.Field()  # str: главное изображение
    images = scrapy.Field()  # list[str]

    crawl_time = scrapy.Field()


class ScrapedJob(scrapy.Item):
    """Вакансия."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    title = scrapy.Field()
    company = scrapy.Field()
    company_url = scrapy.Field()

    salary = scrapy.Field()  # str: "100000-150000 RUB"
    salary_min = scrapy.Field()  # int
    salary_max = scrapy.Field()  # int

    location = scrapy.Field()
    experience = scrapy.Field()  # str: "1-3 года"
    employment_type = scrapy.Field()  # str: полная, частичная, контракт

    description = scrapy.Field()
    requirements = scrapy.Field()  # str
    responsibilities = scrapy.Field()  # str
    skills = scrapy.Field()  # list[str]

    published_date = scrapy.Field()
    is_remote = scrapy.Field()  # bool

    crawl_time = scrapy.Field()


class ScrapedRealty(scrapy.Item):
    """Объявление недвижимости."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    title = scrapy.Field()
    price = scrapy.Field()  # float
    currency = scrapy.Field()
    price_per_sqm = scrapy.Field()  # float

    address = scrapy.Field()
    city = scrapy.Field()
    district = scrapy.Field()

    area = scrapy.Field()  # float: общая площадь (м²)
    living_area = scrapy.Field()  # float
    kitchen_area = scrapy.Field()  # float
    rooms = scrapy.Field()  # int
    floor = scrapy.Field()  # str: "5/15"

    description = scrapy.Field()
    seller = scrapy.Field()
    seller_type = scrapy.Field()  # str: owner, agent, developer

    images = scrapy.Field()  # list[str]

    building_type = scrapy.Field()  # str: кирпич, панель, монолит
    build_year = scrapy.Field()  # int

    crawl_time = scrapy.Field()


class ScrapedAuto(scrapy.Item):
    """Объявление авто."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    title = scrapy.Field()
    price = scrapy.Field()  # float
    currency = scrapy.Field()

    brand = scrapy.Field()
    model = scrapy.Field()
    year = scrapy.Field()  # int
    mileage = scrapy.Field()  # float: км

    engine = scrapy.Field()  # str: "2.0 TDI"
    transmission = scrapy.Field()  # str: автомат, механика
    drive = scrapy.Field()  # str: передний, полный, задний
    body_type = scrapy.Field()  # str: седан, кроссовер
    color = scrapy.Field()

    description = scrapy.Field()
    seller = scrapy.Field()
    images = scrapy.Field()

    vin = scrapy.Field()

    crawl_time = scrapy.Field()


class ScrapedPart(scrapy.Item):
    """Запчасть — результат поиска по артикулу в магазине."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    # Идентификация
    article = scrapy.Field()  # str: артикул (искомый)
    name = scrapy.Field()  # str: название запчасти
    brand = scrapy.Field()  # str: бренд производителя
    sku = scrapy.Field()  # str: SKU / внутренний код

    # Цена
    price = scrapy.Field()  # float: цена в рублях
    currency = scrapy.Field()  # str: RUB, USD, EUR
    old_price = scrapy.Field()  # float: старая цена (если скидка)

    # Наличие и доставка
    availability = scrapy.Field()  # str: in_stock, order, out_of_stock
    delivery_days = scrapy.Field()  # int: дни доставки
    warehouse = scrapy.Field()  # str: склад / магазин

    # Источник
    shop_name = scrapy.Field()  # str: Emex.ru, Exist.ru, etc.
    shop_logo = scrapy.Field()  # str: URL логотипа магазина

    # Ссылки
    product_url = scrapy.Field()  # str: прямая ссылка на товар
    image_url = scrapy.Field()  # str: URL изображения

    crawl_time = scrapy.Field()  # ISO timestamp
    status_code = scrapy.Field()  # int: HTTP статус


class ScrapedContract(scrapy.Item):
    """Госзакупка — контракт с zakupki.gov.ru."""

    url = scrapy.Field()
    domain = scrapy.Field()
    spider_name = scrapy.Field()

    reg_number = scrapy.Field()  # str: номер контракта
    subject = scrapy.Field()  # str: предмет контракта
    price = scrapy.Field()  # float
    currency = scrapy.Field()

    customer = scrapy.Field()  # str: заказчик
    customer_inn = scrapy.Field()
    supplier = scrapy.Field()  # str: поставщик
    region = scrapy.Field()

    publish_date = scrapy.Field()  # str: YYYY-MM-DD
    contract_url = scrapy.Field()

    status = scrapy.Field()  # str: действующий, завершён

    crawl_time = scrapy.Field()
