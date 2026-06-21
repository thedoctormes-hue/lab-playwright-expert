# exist.ru API Research Results

## Найденные эндпоинты

### Поиск (HTML Form → серверный рендер)
```
GET /Price/?pcode=OC471
```
- `<form action="/Price/" method="get">`
- `<input name="pcode" type="search" placeholder="VIN, номер кузова, артикул, наименование">`
- Результаты рендерятся сервер-side в HTML (не SPA!)
- **Проблема**: доступ к ценам требует авторизацию (форма логина появляется)

### API эндпоинты (без авторизации, GET)
```
GET /Api/UniCat/Top?officeId=995
GET /Api/Office/Region
GET /Api/Office?id={id}&deliveryPointId=
GET /Api/Document/Office?officeId=995
GET /Api/Office?id=&deliveryPointId=
```

`/Api/UniCat/Top?officeId=995` — топ-товары:
- Поля: Url, ImageUrl, GroupName, CatalogName, Title, Rating, Description
- Пример: `"/Catalog/Goods/5/183/C4E0CE67"`, `"Airline AFU-M-02 Набор предохранителей"`

### Дополнительно
- Сайт использует React/SPA (файлы: `/ts/Rest/SiteSearchAutoComplete.js`, `/ts/Rest/AutoComplete.js`)
- Поиск через `.inp` input → form submit на `/Price/`
- Playwright крашится при сабмите формы (EPIPE) — защита от ботов (HeadlessChrome header)

## Статус API поиска
- **Прямого REST API для поиска по артикулу НЕ найдено**
- Поиск через HTML form: `GET /Price/?pcode={article}`
- API товаров по каталогу (не поиск): `/Api/UniCat/Top?officeId=...`
- Цены за вторым шагом (авторизация через форму логина)

## Итоговый вывод
exist.ru не имеет открытого API для поиска по артикулу. Поиск — HTML form, цены за логином.
Как workaround — можно парсить HTML `/Price/?pcode=OC471` как обычную страницу (requests + BeautifulSoup).
