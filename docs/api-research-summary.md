# API Research: 7 магазинов автозапчастей

**Дата:** 2026-05-29
**Цель:** найти открытые API/HTML endpoints для поиска запчастей по артикулу

---

## Сводная таблица

| Магазин | Тип | Endpoint | Auth | Цены | Статус |
|---------|-----|----------|------|------|--------|
| autodoc.ru | JSON API | `GET web.autodoc.ru/api/price-service/search/manufacturers?article=OC471` | ❌ Не нужна | ❌ Только производители | ✅ Работает |
| exist.ru | HTML Form | `GET /Price/?pcode=OC471` | ✅ Нужна | ❌ За логином | ⚠️ HTML парсится |
| apex.ru | HTML | `GET /?do=search&article=OC471` | ❌ | ❌ SPA/JS render | ⚠️ Нужен Playwright |
| fobil-auto.ru | HTML Form | `GET /search?pcode=OC471` | Captcha | ❌ CAPTCHA (abcp.ru) | ❌ Закрыт |
| shop.autoeuro.ru | HTML Form | `GET /main/search?article=OC471` | ✅ Нужна | ❌ За авторизацией | ❌ Закрыт |
| mymajor.ru | SPA | Нет search endpoint | ✅ Нужна | ❌ Личный кабинет | ❌ Закрыт |
| emex.ru | — | Timeout | — | — | ❌ Закрыт/DDoS guard |

---

## autodoc.ru ✅ (частично)

### Working API
```
GET https://web.autodoc.ru/api/price-service/search/manufacturers?article=OC471
```
**Без авторизации!** Возвращает JSON:
```json
[{
  "article": "OC 471",
  "manufacturer": {"id": 34, "name": "KNECHT|MAHLE", "imageUrl": "..."},
  "goodsName": "Фильтр масляный",
  "imageUrl": "..."
}]
```

### Не найдено
- Эндпоинт с ценами — ~30 вариантов проверены, все 404
- Цены предоставляются только через SPA-навигацию после выбора производителя
- Angular app, API paths генерируются динамически
- В headless Chrome результаты поиска НЕ рендерятся в DOM
- Playwright EPIPE crash при клике на элемент списка

### Итог
Можно получить список производителей по артикулу чистым `requests.get()`, но цены — только через Playwright с реальным кликом (и даже тогда EPIPE crash).

---

## exist.ru ⚠️

### Поиск
```
GET /Price/?pcode=OC471
```
- HTML form `<form action="/Price/" method="get">`, `<input name="pcode">`
- Серверный рендер (не SPA)
- **Требует авторизацию** — HTML содержит форму логина вместо цен

### Открытые API (без авторизации)
```
GET /Api/UniCat/Top?officeId=995  — каталог товаров
GET /Api/Office/Region            — офисы/регионы
GET /Api/Document/Office?officeId=995
```

### Итог
Можно парсить `/Price/?pcode=OC471` как HTML если авторизоваться. Но Playwright крашится (EPIPE) при сабмите формы — вероятно, бот-защита. Чистый `requests` с сессией после логина — возможно работает.

---

## apex.ru ⚠️

### Форма
```html
<form itemprop="potentialAction">
  <input class="SEARCH_input" id="SEARCH_input" type="text" placeholder="Введите номер запчасти">
</form>
```

Страница `/?do=search&article=OC471` возвращает 200 с SPA-рендериным HTML. API endpoint `/api/site/1.0/` упомянут в HTML но все варианты поиска через него дают 404.

Нужен Playwright для рендера результатов.

---

## fobil-auto.ru ❌

### Платформа: ABCP.ru
```html
<form action="/search" method="get" name="searchform">
  <input name="pcode" type="search">
</form>
```

Playwright показывает **CAPTCHA**: *"ваш ip-адрес находится в спике подозрительных. Обычно такое происходит с адресами мобильных операторов"*

Заблокировано через abcp.ru платформу (бот-защита).

---

## shop.autoeuro.ru ❌

```html
<form action="/main/search" name="search_one" method="get">
```

Заголовок страницы: **"ВЫ НЕ АВТОРИЗОВАНЫ"**. Поиск возвращает HTML но без ценовых данных — требуется авторизация.

---

## mymajor.ru ❌

Полностью закрыт авторизацией. Главная страница — форма входа/регистрации (личный кабинет). Нет публичного поиска по артикулу.

---

## emex.ru ❌

HTTPS соединение завершилось по timeout. DDoS-защита или Cloudflare. Публичный endpoint для поиска не найден (по DNS/network эмпирике).

---

## MVP Рекомендация

**Вариант 1 — Playwright-решение (рекомендуется для старта):**
- Использовать текущий Scrapy + scrapy-playwright стек
- autodoc.ru: `requests.get()` для списка производителей + Playwright для цен через CDP intercept
- exist.ru: `requests` с сессией (POST логин → GET /Price/?pcode=OC471 → парсить HTML)
- apex.ru: Playwright + ожидание рендера SPA
- fobil-auto/emex/mymajor: закрыты, отлично для MVP

**Вариант 2 — API-первого подхода:**
- autodoc.ru: ✅ работает без браузера (`manufacturers` endpoint)
- exist.ru: ⚠️ работает если авторизоваться (парсить HTML)
- Остальные: ❌ требуют браузер

Архитектура: гибрид — autodoc через requests, exist через Playwright сессию, остальные ограничить depth.
