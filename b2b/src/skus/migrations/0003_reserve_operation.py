# Generated 2026-06-03

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skus", "0002_sku_accounting_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReserveOperation",
            fields=[
                (
                    "idempotency_key",
                    models.UUIDField(primary_key=True, serialize=False),
                ),
                ("result", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Операция резервирования",
                "verbose_name_plural": "Операции резервирования",
            },
        ),
    ]
