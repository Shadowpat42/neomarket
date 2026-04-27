# NeoMarket

Учебный проект маркетплейса NeoMarket.

## Сервисы

- `b2b/` — кабинет продавца: товары, SKU, категории, накладные
- `b2c/` — витрина покупателя: каталог, корзина, избранное, главная
- `moderation/` — модерация товаров

## Текущий статус

Поднят базовый каркас трёх Django/DRF сервисов.

## Локальный запуск

### B2B

```bash
cd b2b/src
python manage.py migrate
python manage.py runserver 8001
```

Проверка:

```text
http://127.0.0.1:8001/api/v1/products/550e8400-e29b-41d4-a716-446655440000
```

### B2C

```bash
cd b2c/src
python manage.py migrate
python manage.py runserver 8002
```

Проверка:

```text
http://127.0.0.1:8002/api/v1/favorites
```

### Moderation

```bash
cd moderation/src
python manage.py migrate
python manage.py runserver 8003
```

## Дальше

1. Реализовать B2B по OpenAPI-спеке
2. Реализовать B2C по OpenAPI-спеке
3. Реализовать Moderation по OpenAPI-спеке
4. Добавить PostgreSQL и Docker
