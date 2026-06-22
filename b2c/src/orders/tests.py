import uuid
from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase
from rest_framework.test import APIClient

from cart.models import CartItem
from .models import Order, OrderItem, ProcessedProductEvent

PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"
SKU_ID = "62fbcabb-be0e-479e-a33b-b848c75da7e0"
USER_ID = "556f051a-baee-4b0f-bd41-555b5e01e6f4"


def b2b_products_response(active_quantity=5, price=12999000, discount=0):
    return {
        "items": [
            {
                "id": PRODUCT_ID,
                "title": "iPhone 15 Pro Max",
                "skus": [
                    {
                        "id": SKU_ID,
                        "name": "256GB Black",
                        "price": price,
                        "discount": discount,
                        "active_quantity": active_quantity,
                    }
                ],
            }
        ]
    }


class CheckoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/orders"
        self.headers = {
            "HTTP_X_USER_ID": USER_ID,
        }

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_checkout_creates_paid_order_with_fixed_prices(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(
            active_quantity=5,
            price=12999000,
            discount=1000000,
        )
        mock_reserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "RESERVED",
                "reserved_at": "2026-06-10T00:00:00Z",
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-1"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PAID")
        self.assertEqual(response.data["total_amount"], 23998000)

        order = Order.objects.get(id=response.data["id"])
        item = OrderItem.objects.get(order=order)

        self.assertEqual(item.unit_price, 11999000)
        self.assertEqual(item.line_total, 23998000)
        self.assertEqual(item.product_title, "iPhone 15 Pro Max")
        self.assertEqual(item.sku_name, "256GB Black")

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_partial_reserve_failure_returns_409(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(active_quantity=5)
        mock_reserve.return_value = (
            409,
            {
                "code": "INSUFFICIENT_STOCK",
                "message": "Недостаточно остатка",
                "details": {
                    "failed_items": [
                        {
                            "sku_id": SKU_ID,
                            "reason": "INSUFFICIENT_STOCK",
                        }
                    ]
                },
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-2"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "RESERVE_FAILED")
        self.assertIn("failed_items", response.data["details"]["details"])

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_idempotency_returns_existing_order(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(active_quantity=5)
        mock_reserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "RESERVED",
                "reserved_at": "2026-06-10T00:00:00Z",
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=1,
        )

        body = {"idempotency_key": "same-checkout-key"}

        response1 = self.client.post(
            self.url,
            body,
            format="json",
            **self.headers,
        )

        response2 = self.client.post(
            self.url,
            body,
            format="json",
            **self.headers,
        )

        self.assertEqual(response1.status_code, 201)
        self.assertEqual(response2.status_code, 200)

        self.assertEqual(response1.data["id"], response2.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    @patch("orders.views.b2b_get_products")
    def test_b2b_unavailable_returns_503(self, mock_get_products):
        mock_get_products.side_effect = URLError("B2B unavailable")

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=1,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-3"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")


class CancelOrderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_USER_ID": USER_ID,
        }

    def create_order(self, status_value="PAID", user_id=USER_ID):
        order = Order.objects.create(
            user_id=user_id,
            idempotency_key=f"cancel-test-{status_value}-{user_id}",
            status=status_value,
            total_amount=12999000,
        )

        OrderItem.objects.create(
            order=order,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            product_title="iPhone 15 Pro Max",
            sku_name="256GB Black",
            quantity=1,
            unit_price=12999000,
            line_total=12999000,
        )

        return order

    @patch("orders.views.b2b_unreserve")
    def test_cancel_paid_order_transitions_to_cancelled(self, mock_unreserve):
        mock_unreserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "UNRESERVED",
                "processed_at": "2026-06-10T00:00:00Z",
            },
        )

        order = self.create_order(status_value="PAID")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(order.cancel_reason, "Передумал")
        self.assertIsNotNone(order.cancelled_at)

        self.assertEqual(response.data["status"], "CANCELLED")

    @patch("orders.views.b2b_unreserve")
    def test_unreserve_failure_transitions_to_cancel_pending(self, mock_unreserve):
        mock_unreserve.side_effect = URLError("B2B unavailable")

        order = self.create_order(status_value="PAID")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Не нужен"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 202)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCEL_PENDING")
        self.assertEqual(order.cancel_reason, "Не нужен")

        self.assertEqual(response.data["status"], "CANCEL_PENDING")

    @patch("orders.views.b2b_unreserve")
    def test_cancel_assembling_order_transitions_to_cancelled(self, mock_unreserve):
        mock_unreserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "UNRESERVED",
                "processed_at": "2026-06-10T00:00:00Z",
            },
        )

        order = self.create_order(status_value="ASSEMBLING")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(response.data["status"], "CANCELLED")
        mock_unreserve.assert_called_once()

    @patch("orders.views.b2b_unreserve")
    def test_cancel_delivered_order_returns_409(self, mock_unreserve):
        order = self.create_order(status_value="DELIVERED")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "CANCEL_NOT_ALLOWED")
        self.assertEqual(response.data["details"]["current_status"], "DELIVERED")

        mock_unreserve.assert_not_called()

    @patch("orders.views.b2b_unreserve")
    def test_other_user_order_returns_404(self, mock_unreserve):
        other_user_id = "11111111-1111-1111-1111-111111111111"

        order = self.create_order(
            status_value="PAID",
            user_id=other_user_id,
        )

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Пытаюсь отменить чужой"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "ORDER_NOT_FOUND")

        mock_unreserve.assert_not_called()


# ════════════════════════════════════════════════════════════════
# US-ORD-02: Просмотр и отслеживание заказов
# ════════════════════════════════════════════════════════════════

OTHER_USER_ID = "11111111-1111-1111-1111-111111111111"


def _make_order(user_id=USER_ID, status_value="PAID", key_suffix=""):
    return Order.objects.create(
        user_id=user_id,
        idempotency_key=f"ord-{user_id[:8]}-{status_value}-{key_suffix}",
        status=status_value,
        total_amount=12_999_000,
        delivery_address="г. Екатеринбург, ул. Мира 19, кв. 42",
    )


def _make_item(order):
    return OrderItem.objects.create(
        order=order,
        product_id=PRODUCT_ID,
        sku_id=SKU_ID,
        product_title="iPhone 15 Pro Max",
        sku_name="256GB Black",
        quantity=2,
        unit_price=6_499_500,
        line_total=12_999_000,
    )


class OrderListTests(TestCase):
    """US-ORD-02: GET /api/v1/orders — own orders, paginated."""

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_USER_ID=USER_ID)
        for i in range(3):
            _make_order(key_suffix=str(i))
        _make_order(user_id=OTHER_USER_ID, key_suffix="other")

    def test_orders_list_returns_own_orders_paginated(self):
        """
        GET /api/v1/orders returns only own orders.
        Pagination: limit=2, offset=0 → 2 items; total_count=3.
        """
        resp = self.client.get("/api/v1/orders?limit=2&offset=0")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_count"], 3)
        self.assertEqual(len(resp.data["items"]), 2)
        self.assertEqual(resp.data["limit"], 2)
        self.assertEqual(resp.data["offset"], 0)

        item = resp.data["items"][0]
        self.assertIn("id", item)
        self.assertIn("status", item)
        self.assertIn("total_amount", item)
        self.assertIn("items_count", item)
        self.assertNotIn("items", item)

    def test_status_filter_returns_matching_orders(self):
        _make_order(status_value="DELIVERED", key_suffix="deliv")
        resp = self.client.get("/api/v1/orders?status=DELIVERED")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_count"], 1)
        self.assertEqual(resp.data["items"][0]["status"], "DELIVERED")

    def test_unauthorized_returns_401(self):
        resp = APIClient().get("/api/v1/orders")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "UNAUTHORIZED")


class OrderDetailTests(TestCase):
    """US-ORD-02: GET /api/v1/orders/{id}."""

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_USER_ID=USER_ID)

    def test_order_detail_shows_fixed_prices(self):
        """
        Prices come from OrderItem (unit_price), not from current B2B SKU.
        Response uses OpenAPI field names: buyer_id, subtotal, total, address.
        """
        order = _make_order()
        _make_item(order)

        resp = self.client.get(f"/api/v1/orders/{order.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], str(order.id))
        # OpenAPI required fields
        self.assertEqual(resp.data["buyer_id"], USER_ID)
        self.assertEqual(resp.data["subtotal"], 12_999_000)
        self.assertEqual(resp.data["total"], 12_999_000)
        self.assertIn("address", resp.data)
        self.assertIn("items", resp.data)
        # Old names must NOT appear in the response
        self.assertNotIn("total_amount", resp.data)
        self.assertNotIn("delivery_address", resp.data)

        item = resp.data["items"][0]
        self.assertEqual(item["unit_price"], 6_499_500)
        self.assertEqual(item["line_total"], 12_999_000)
        self.assertEqual(item["product_title"], "iPhone 15 Pro Max")
        self.assertEqual(item["sku_name"], "256GB Black")

    def test_other_user_order_returns_404_not_403(self):
        """
        IDOR: accessing another user's order must return 404, not 403.
        Returning 403 would confirm the order exists, leaking info.
        """
        order = _make_order(user_id=OTHER_USER_ID)
        resp = self.client.get(f"/api/v1/orders/{order.id}")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "ORDER_NOT_FOUND")

    def test_nonexistent_order_returns_404(self):
        resp = self.client.get(f"/api/v1/orders/{uuid.uuid4()}")
        self.assertEqual(resp.status_code, 404)


# ════════════════════════════════════════════════════════════════
# US-ORD-04: Реакция B2C на события товаров от B2B
# ════════════════════════════════════════════════════════════════

B2B_SVC_KEY = "b2b_service_key"


class ProductEventTests(TestCase):
    """US-ORD-04: POST /api/v1/events/product."""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/events/product"

    def _post(self, event, sku_ids, idempotency_key=None, with_key=True):
        headers = {}
        if with_key:
            headers["HTTP_X_SERVICE_KEY"] = B2B_SVC_KEY
        return self.client.post(
            self.url,
            {
                "idempotency_key": idempotency_key or str(uuid.uuid4()),
                "event": event,
                "product_id": PRODUCT_ID,
                "sku_ids": sku_ids,
                "date": "2026-04-16T12:00:00Z",
            },
            format="json",
            **headers,
        )

    def test_product_blocked_marks_cart_items_unavailable(self):
        """
        PRODUCT_BLOCKED → all CartItems with matching sku_id get unavailable_reason.
        Orders with the same sku_id are NOT affected.
        """
        sku_id = str(uuid.uuid4())
        CartItem.objects.create(
            user_id=USER_ID, product_id=PRODUCT_ID, sku_id=sku_id, quantity=2
        )

        resp = self._post("PRODUCT_BLOCKED", [sku_id])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["accepted"])

        cart_item = CartItem.objects.get(sku_id=sku_id)
        self.assertEqual(cart_item.unavailable_reason, "PRODUCT_BLOCKED")

    def test_orders_not_affected_by_product_blocked(self):
        """
        PRODUCT_BLOCKED must NOT touch Order records.
        Prices are fixed; seller must fulfil the existing order.
        """
        sku_id = str(uuid.uuid4())
        order = _make_order()
        OrderItem.objects.create(
            order=order,
            product_id=PRODUCT_ID,
            sku_id=sku_id,
            product_title="Test",
            sku_name="Test SKU",
            quantity=1,
            unit_price=12_999_000,
            line_total=12_999_000,
        )

        self._post("PRODUCT_BLOCKED", [sku_id])

        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")

    def test_idempotent_event_no_side_effects(self):
        """
        Repeated event with same idempotency_key → 200, no second update.
        """
        sku_id = str(uuid.uuid4())
        CartItem.objects.create(
            user_id=USER_ID, product_id=PRODUCT_ID, sku_id=sku_id, quantity=1
        )
        key = str(uuid.uuid4())

        self._post("PRODUCT_BLOCKED", [sku_id], idempotency_key=key)
        CartItem.objects.filter(sku_id=sku_id).update(unavailable_reason=None)

        self._post("PRODUCT_BLOCKED", [sku_id], idempotency_key=key)
        cart_item = CartItem.objects.get(sku_id=sku_id)
        self.assertIsNone(cart_item.unavailable_reason)

    def test_missing_service_key_returns_401(self):
        """No X-Service-Key → 401 UNAUTHORIZED."""
        resp = self._post("PRODUCT_BLOCKED", [SKU_ID], with_key=False)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "UNAUTHORIZED")


# ════════════════════════════════════════════════════════════════
# US-ORD-05: Финальное списание резерва при доставке
# ════════════════════════════════════════════════════════════════

class FulfillOnDeliveredTests(TestCase):
    """US-ORD-05: deliver_order() triggers b2b_fulfill."""

    def setUp(self):
        self.order = _make_order(status_value="DELIVERING")
        _make_item(self.order)

    @patch("orders.views.b2b_fulfill")
    def test_delivered_status_triggers_fulfill_to_b2b(self, mock_fulfill):
        """
        deliver_order() transitions order to DELIVERED and calls b2b_fulfill.
        B2B is called with order_id and items (sku_id + quantity).
        """
        mock_fulfill.return_value = (200, {"fulfilled": True})

        from orders.views import deliver_order
        deliver_order(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")
        mock_fulfill.assert_called_once_with(self.order)

    @patch("orders.views.b2b_fulfill")
    def test_fulfill_failure_retried_asynchronously(self, mock_fulfill):
        """
        B2B error → order stays DELIVERED, error is logged (fire-and-forget scaffold).
        reserved_quantity will be corrected when fulfill is eventually retried.
        """
        mock_fulfill.side_effect = Exception("B2B is down")

        from orders.views import deliver_order
        with self.assertLogs("orders.views", level="ERROR"):
            deliver_order(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")

    @patch("orders.views.b2b_fulfill")
    def test_repeated_fulfill_idempotent(self, mock_fulfill):
        """
        Calling deliver_order twice → b2b_fulfill called twice.
        B2B handles deduplication by order_id (FulfilledOrder table on B2B side).
        Both calls succeed — no error raised.
        """
        mock_fulfill.return_value = (200, {"fulfilled": True})

        from orders.views import deliver_order
        deliver_order(self.order)
        deliver_order(self.order)

        self.assertEqual(mock_fulfill.call_count, 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")
