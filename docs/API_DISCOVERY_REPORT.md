# API Discovery Report — 7 магазинов автозапчастей

**Дата**: 2026-05-28
**Тестовый артикул**: OC471 (Фильтр масляный)
**Стратегия**: переход от CSS-селекторов к direct HTTP API

---

## Сводная таблица

| Магазин | Поиск API | Цены API | Статус | Сложность |
|---------|-----------|----------|--------|-----------|
| autodoc.ru | ✅ | ⚠️ 401 | PARTILOW | Высокая (OIDC auth) |
| apex.ru | ✅ | ✅ | ✅ РАБОТАЕТ | Низкая |
| exist.ru | ⚠️ WebForms | ⚠️ WebForms | PARTILOW | Высокая (ViewState) |
| autoeuro.ru | ✅ | ⚠️ sign token | PARTILOW | Средняя |
| fobil-auto.ru | ✅ URL | ❓ SPA-render | PARTILOW | Средняя |
| mymajor.ru | ❌ | ❌ | ❌ НЕТ API | — |
| emex.ru | ❌ timeout | ❌ | ❌ BLOCKED | Cloudflare |

---

## 1. autodoc.ru — PARTIALLY WORKING

### Архитектура
- SPA (Angular) + microservices на `web.autodoc.ru`
- Авторизация: OIDC через `login.autodoc.ru` (IdentityServer 4)
- client_id: `Angular`, grant_type: `password`

### Working endpoints

**Поиск производителей по артикулу:**
```
GET https://web.autodoc.ru/api/price-service/search/manufacturers?article=OC471
→ {"items":[{"article":"OC471","manufacturer":{"name":"KNECHT | MAHLE | BEHR","id":34},"goodsName":"Фильтр масляный","imageUrl":"https://images.autodoc.ru/goods/34/OC471/..."}]}
```

**Цена товара (публично, но 0 для неавторизованных):**
```
GET https://web.autodoc.ru/api/goods-service/goods/price?goodsId=34_OC471
→ {"minimalPrice":0.00,"minimalDeliveryDays":0}
```

**Информация о товаре (публично):**
```
GET https://web.autodoc.ru/api/goods-service/goods/info?goodsId=34_OC471
→ {"isFavorite":false,"inStock":2,"items":[]}
```

### Требующие авторизации (401)
```
GET https://web.autodoc.ru/api/price-service/price-list/goods-info?article=OC471&manufacturerId=34
GET https://web.autodoc.ru/api/price-service/price-list/analogs?article=OC471&manufacturerId=34
GET https://web.autodoc.ru/api/price-service/price-list/access-levels
```

### OIDC Auth flow
```python
# Получение токена (client_id=Angular, password grant)
r = requests.post('https://login.autodoc.ru/connect/token', data={
    'grant_type': 'password',
    'client_id': 'Angular',
    'username': 'any@email.com',
    'password': 'any',
    'scope': 'openid offline_access'
})
token = r.json()['access_token']
# Но цены всё равно 0 — нужен реальный аккаунт
```

### Все обнаруженные сервисы
- `/api/price-service/` — прайс-листы, поиск, история
- `/api/goods-service/` — товары, цены, совместимость, отзывы
- `/api/catalog-universal-service/` — каталог категорий
- `/api/delivery-service/` — доставка
- `/api/order-service/` — заказы
- `/api/balance-service/` — баланс и оплата
- `/api/auth-service/` — регистрация, авторизация
- `/api/banner-service/` — баннеры
- `/api/chat-service/` — чат-бот
- `/api/company-service/` — новости
- `/api/marketing-service/` — метаданные
- `/api/registration/` — способы регистрации

### Рекомендация
Требуется регистрация аккаунта для получения цен. Без авторизации — только поиск производителей.

---

## 2. apex.ru — ✅ ПОЛНОСТЬЮ РАБОТАЕТ

### Архитектура
- Серверный рендер + jQuery AJAX
- Куки-сессия (PHPSESSID), без авторизации

### Working endpoints

**Поиск по артикулу:**
```
GET https://apex.ru/ajax/catalog?todo=search_articles&term=OC471
→ {"result":"SUCCESS","list":[
    {"type":"a","code":"ЦБ00749690","url":"/autoparts/Mahle/OC471",
     "mark":"Mahle ORIGINAL","article":"OC471","name":"Фильтр масляный Renault"}
  ]}
```

**Полный прайс-лист с ценами:**
```
POST https://apex.ru/ajax/pricelist
  data: todo=get&code=ЦБ00749690
→ {"result":"SUCCESS","pricelist":[
    {"mark":"Alco","article":"SP1039","name":"Фильтр масляный...",
     "offers":[
       {"offercode":"s_100737732_002427_2828","price":630,"days":1,"qty":149,"reliability":33},
       {"offercode":"s_100737732_002640_2828","price":630,"days":3,"qty":728,"reliability":0},
       ...
     ]},
    ...
  ]}
```

### Структура offers
Каждое предложение содержит:
- `price` — цена в рублях (int)
- `days` — срок доставки (дни)
- `qty` — количество на складе
- `reliability` — надёжность поставщика (0-100)
- `is_returnable` — возврат возможен
- `prepay` — предоплата обязательна
- `dt_arrive` — дата поступления

### Страница товара (HTML парсинг)
```
GET https://apex.ru/autoparts/Mahle/OC471?ms=1
→ H1: "Mahle ORIGINAL OC471 Фильтр масляный Renault"
```

### Рекомендация
✅ Лучший кандидат для интеграции. Полный API без авторизации.

---

## 3. exist.ru — PARTIALLY WORKING (WebForms)

### Архитектура
- ASP.NET WebForms с ViewState
- Поиск через POST с `__VIEWSTATE`

### Форма поиска
```
POST https://exist.ru/Price/
  __VIEWSTATE: <длинная строка>
  __VIEWSTATEGENERATOR: 9BF66EA1
  __EVENTVALIDATION: <длинная строка>
  ctl00$ctl00$b$b$tbTextSearch: OC471
  ctl00$ctl00$b$b$ctl00: Поиск
→ Редирект на /Price/Empty.aspx (пустые результаты без полного браузерного окружения)
```

### Проблема
ASP.NET WebForms требует `<button>` или `__EVENTTARGET` вместо простого submit. Без полного рендеринга JS — ViewState не обрабатывается корректно.

### Рекомендация
Требуется Playwright с полным рендерингом для корректной работы ViewState. Либо обратиться к API `/Api/*` (если есть).

---

## 4. autoeuro.ru — PARTIALLY WORKING

### Архитектура
- SPA на `autoeuro.ru`, старый jQuery frontend на `shop.autoeuro.ru`
- Микросервисная архитектура

### Working endpoints

**Поиск по артикулу (публично):**
```
GET https://products.svc.autoeuro.ru/search-by-code?code=OC471
→ [{"mega_id":"...","maker_id":123,"maker":"MAHLE","code":"OC471","name":"Фильтр масляный"}]
```

**Категории:**
```
GET https://shopcat-api.autoeuro.ru/api/v2/category
```

**Бренды:**
```
GET https://autoeuro.ru/v2/oem/brands
```

**Пункты выдачи:**
```
GET https://shipment.autoeuro.ru/api/list/points/coordinate
```

### Auth (для цен)
```
POST https://autoeuro.ru/v1/auth/sign
→ customer.id + sign token

POST https://basket.svc.autoeuro.ru/api/v1/list (с customer sign)
→ корзина с ценами
```

### Рекомендация
Для получения цен нужен `customer.id + sign token` через `POST /v1/auth/sign` (любой номер телефона).

---

## 5. fobil-auto.ru — PARTIALLY WORKING

### Архитектура
- SPA, серверный рендер с `<base href="/">`

### Поиск по артикулу
```
GET https://fobil-auto.ru/search?pcode=OC471
→ 200, OC471 найден в HTML, но цены рендерятся через SPA (пустые в HTML)
```

### Рекомендация
HTML-парсинг возможен для поиска, но цены требуют Playwright rendering.

---

## 6. mymajor.ru — ❌ НЕТ API

### Анализ
- Серверный рендер, нет SPA
- `/api/*` — редиректят на HTML (fallback)
- POST /api/search — 39KB HTML (серверный поиск)
- Нет поиска по артикулу на главной (только checkbox)
- CSRF-токен в meta-тегах

### Рекомендация
Сайт-визитка без функционала поиска по артикулу. Не подходит для парсинга запчастей.

---

## 7. emex.ru — ❌ BLOCKED

### Анализ
- HTTP и HTTPS timeout (15s)
- Cloudflare/DDoS Guard защита
- Нет headless-доступа

### Рекомендация
Блокирован. Требуется разрешение от администрации или прокси с "чистого" IP.

---

## Рекомендации по реализации

### Топ-1: apex.ru
```python
import requests

def apex_search(article):
    s = requests.Session()
    s.get('https://apex.ru/')
    r = s.get('https://apex.ru/ajax/catalog?todo=search_articles&term=' + article)
    return r.json()['list']

def apex_prices(code):
    s = requests.Session()
    s.get('https://apex.ru/')
    r = s.post('https://apex.ru/ajax/pricelist', data={'todo': 'get', 'code': code})
    return r.json()['pricelist']
```

### Топ-2: autoeuro.ru (поиск без цен)
```python
def autoeuro_search(code):
    r = requests.get('https://products.svc.autoeuro.ru/search-by-code?code=' + code)
    return r.json()
```

### Топ-3: autodoc.ru (поиск без цен)
```python
def autodoc_search(article):
    r = requests.get('https://web.autodoc.ru/api/price-service/search/manufacturers?article=' + article)
    return r.json()['items']
```

### Для exist.ru и fobil-auto.ru
Требуется Playwright с полным браузерным рендерингом (headful mode с GPU).

### Для emex.ru
Требуется разрешение на доступ или обход Cloudflare.
