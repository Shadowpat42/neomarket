# neomarket-shared-models

Абстрактные модели Django для микросервисов NeoMarket (B2B, B2C, Moderation).

Пакет предоставляет общие абстрактные модели, которые используются во всех сервисах для унификации структуры данных: изображения, характеристики товаров и т.д. Конкретные модели в каждом сервисе наследуются от этих абстрактных и добавляют свои связи (ForeignKey, ManyToMany).

## Что внутри

- `BaseImage` – абстрактная модель для изображений (поля `url`, `ordering`).
- `BaseCharacteristic` – абстрактная модель для характеристик (поля `name`, `value`).

## Как использовать

```bash
# b2b
cd ../b2b
pip install -e ../shared-models

# b2c
cd ../b2c
pip install -e ../shared-models

# moderation
cd ../moderation
pip install -e ../shared-models
```

```bash
from shared_models.models import BaseImage, BaseCharacteristic
```

## Как обновить общую модель

Измените нужную абстрактную модель в shared_models/models.py.

В каждом сервисе, где есть конкретная модель, наследующая от изменённой абстрактной модели, создайте новую миграцию:

```bash
python manage.py makemigrations
python manage.py migrate
```

Перезапустите сервисы.

## Примичания

Абстрактные модели не создают таблиц в базе данных.

Не пытайтесь использовать BaseImage.objects.create() – это вызовет ошибку.

Пакет не нужно добавлять в INSTALLED_APPS, но если добавите – ничего не сломается.