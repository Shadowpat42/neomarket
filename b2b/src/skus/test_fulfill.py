"""
US-B2B-10: финальное списание резерва при доставке (fulfill).

ADR — идемпотентность по order_id
  Рассматривались три подхода:
  A) Отдельная таблица fulfilled_orders (выбрано).
     Преимущества: риск двойного списания при retry равен нулю — первый INSERT
     фиксирует факт выполнения, повторный SELECT находит запись и возвращает
     кэшированный ответ без любых изменений в SKU. Сложность: минимальная —
     одна дополнительная таблица, один SELECT в транзакции.
  B) Поле last_fulfilled_order_id в модели SKU.
     Не атомарно для multi-SKU заказов; race-condition если два SKU одного
     заказа обновляются параллельно.
  C) Проверка через reserved_quantity.
     Не позволяет отличить «уже выполнен» от «резерва никогда не было».
     Повторный вызов после частичного retry может дважды уменьшить резерв.
  Выбрано A: наименьший риск двойного списания + простота реализации.

Сценарии:
  fulfill_decreases_reserved_quantity
  active_quantity_unchanged
  idempotent_fulfill_no_double_deduction
  missing_service_key_returns_401
"""
import uuid

from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from products.models import Category, Image, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, SKUImage

URL = "/api/v1/inventory/fulfill"


def _make_product(category):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    seller = User.objects.create_user(
        email=f"seller_{uuid.uuid4().hex[:8]}@test.com",
        password="pass1234",
        first_name="S",
        last_name="E",
        company_name="Co",
        phone=f"+7{uuid.uuid4().int % 10_000_000_000:010d}",
    )
    product = Product.objects.create(
        seller_id=seller.id,
        category=category,
        title="iPhone 15",
        description="Desc",
        status=BaseProductStatus.MODERATED,
    )
    Image.objects.create(product=product, url="https://cdn.example.com/img.jpg", ordering=0)
    return product


def _make_sku(product, stock=10, reserved=3):
    sku = SKU.objects.create(
        product=product,
        name="128GB",
        price=100_000_00,
        cost_price=70_000_00,
        stock_quantity=stock,
        reserved_quantity=reserved,
    )
    SKUImage.objects.create(sku=sku, url="https://cdn.example.com/sku.jpg", ordering=0)
    return sku


class FulfillTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_SERVICE_KEY=settings.B2C_SERVICE_KEY)
        self.category = Category.objects.create(name="Phones")
        self.product = _make_product(self.category)
        # stock=10, reserved=3, active=7
        self.sku = _make_sku(self.product, stock=10, reserved=3)

    def _payload(self, order_id=None, qty=2):
        return {
            "order_id": order_id or str(uuid.uuid4()),
            "items": [{"sku_id": str(self.sku.id), "quantity": qty}],
        }

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_fulfill_decreases_reserved_quantity(self):
        """
        POST /api/v1/inventory/fulfill decreases reserved_quantity by the given quantity.
        Initial: stock=10, reserved=3. Fulfill qty=2 → reserved=1.
        """
        resp = self.client.post(URL, self._payload(qty=2), format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "FULFILLED")

        self.sku.refresh_from_db()
        self.assertEqual(self.sku.reserved_quantity, 1)  # 3 - 2 = 1
        self.assertEqual(self.sku.stock_quantity, 8)     # 10 - 2 = 8

    def test_active_quantity_unchanged(self):
        """
        active_quantity = stock - reserved must NOT change after fulfill.
        Before: active = 10 - 3 = 7. After fulfill qty=2: stock=8, reserved=1 → active=7.
        """
        active_before = self.sku.stock_quantity - self.sku.reserved_quantity  # 7

        self.client.post(URL, self._payload(qty=2), format="json")

        self.sku.refresh_from_db()
        active_after = self.sku.stock_quantity - self.sku.reserved_quantity
        self.assertEqual(active_after, active_before,
                         "active_quantity must remain unchanged after fulfill")

    def test_idempotent_fulfill_no_double_deduction(self):
        """
        Repeat POST with the same order_id returns 200 without changing data again.
        """
        order_id = str(uuid.uuid4())
        payload = self._payload(order_id=order_id, qty=2)

        resp1 = self.client.post(URL, payload, format="json")
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        self.sku.refresh_from_db()
        reserved_after_first = self.sku.reserved_quantity  # 1
        stock_after_first = self.sku.stock_quantity        # 8

        # Second call — same order_id
        resp2 = self.client.post(URL, payload, format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        self.sku.refresh_from_db()
        # Must not change
        self.assertEqual(self.sku.reserved_quantity, reserved_after_first,
                         "reserved_quantity must not decrease on duplicate fulfill")
        self.assertEqual(self.sku.stock_quantity, stock_after_first,
                         "stock_quantity must not decrease on duplicate fulfill")

    def test_missing_service_key_returns_401(self):
        """
        Request without X-Service-Key → 401 or 403.
        """
        client = APIClient()  # no credentials
        resp = client.post(URL, self._payload(), format="json")
        self.assertIn(resp.status_code,
                      [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
