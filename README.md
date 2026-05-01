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

## b2b

# Регистрация

```bash
curl -X POST http://127.0.0.1:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seller@test.com",
    "password": "testpass123",
    "first_name": "Иван",
    "last_name": "Петров",
    "middle_name": "Иванович",
    "company_name": "ООО Тест",
    "phone": "+79991234567"
  }'
```

# Логин

```bash
curl -X POST http://127.0.0.1:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "seller@test.com", "password": "testpass123"}'
```

```bash
{"refresh":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3ODIzNDc5OCwiaWF0IjoxNzc3NjI5OTk4LCJqdGkiOiJhNGViMDA0Mzk4YjA0ZGE1OTgyZDkyMzYxYWJhOTQ2YiIsInVzZXJfaWQiOiJkMTg0ZDUzNy1iZGI2LTQ0NDAtYTY4NC0xYjc5YjIxYzE1MzAifQ.SpxsaxFxTivhhYDli5c37SkKyy1sgHIu7Mkxfo4j9Zo","access":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc3NjMxNzk4LCJpYXQiOjE3Nzc2Mjk5OTgsImp0aSI6IjFiNDIyOTVlMTc0MzRiNmI4OWViYzY2YjlkNTc4OGY5IiwidXNlcl9pZCI6ImQxODRkNTM3LWJkYjYtNDQ0MC1hNjg0LTFiNzliMjFjMTUzMCJ9.XxzPLc5tLSwu122JJ6Nleb0SQUK8JufIGc7xTfKh2Vo"}
```

в фронте надо 
```bash
ACCESS_TOKEN="выданный токен refresh"
REFRESH_TOKEN="выданный токен access"
```

# Профиль (GET)

```bash
curl -X GET http://127.0.0.1:8001/api/v1/seller/profile \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

# Обновление профиля

```bash
curl -X PATCH http://127.0.0.1:8001/api/v1/seller/profile/update \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"first_name": "НовоеИмя"}'
```

# Создание товара (категория нужна, в админке создать)
```bash
curl -X POST http://127.0.0.1:8001/api/v1/products/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "title": "iPhone 15 Pro Max",
    "description": "Флагман",
    "category_id": "UUID_КАТЕГОРИИ",
    "images": [{"url": "https://example.com/1.jpg", "ordering": 0}],
    "characteristics": [{"name": "Бренд", "value": "Apple"}]
  }'
```

# Список своих товаров

```bash
curl -X GET http://127.0.0.1:8001/api/v1/products/my \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

# product по id

```bash
curl -X GET http://127.0.0.1:8001/api/v1/products/33a30226-0d92-4720-9028-98fddcb33d7b \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```