# Generated 2026-06-03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0004_blocking_reason_and_field_reports"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedModerationEvent",
            fields=[
                (
                    "idempotency_key",
                    models.UUIDField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Обработанное событие модерации",
                "verbose_name_plural": "Обработанные события модерации",
            },
        ),
    ]
