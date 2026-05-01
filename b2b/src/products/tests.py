import uuid
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from products.models import Product, Category, Image, Characteristic
from shared_models.models import BaseProductStatus


class ProductAPITestCase(APITestCase):
    def setUp(self):
        # Пользователь (продавец)
        self.user = User.objects.create_user(
            username='seller',
            password='testpass123'
        )
        self.user_id = self.user.id   # IntegerField в модели Product

        # Клиент с аутентификацией
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Категория
        self.category = Category.objects.create(
            id=uuid.uuid4(),
            name='Смартфоны'
        )

        # URL из urls.py (с именами)
        self.products_list_url = reverse('product-list-create')
        # self.my_products_url = reverse('my-products')

    # ========== CREATE ==========
    def test_create_product_success(self):
        """Успешное создание товара"""
        data = {
            'title': 'iPhone 15',
            'description': 'Флагман',
            'category_id': str(self.category.id),
            'images': [{'url': 'http://example.com/1.jpg', 'ordering': 0}],
            'characteristics': [{'name': 'Бренд', 'value': 'Apple'}]
        }
        response = self.client.post(self.products_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 1)
        product = Product.objects.first()
        self.assertEqual(product.title, 'iPhone 15')
        self.assertEqual(product.seller_id, self.user_id)
        self.assertEqual(product.images.count(), 1)
        self.assertEqual(product.characteristics.count(), 1)

    def test_create_product_missing_category(self):
        """Несуществующая категория -> 400, ошибка в поле category_id"""
        data = {
            'title': 'iPhone',
            'category_id': str(uuid.uuid4()),
            'images': [],
            'characteristics': []
        }
        response = self.client.post(self.products_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data.get('errors', {})
        self.assertIn('category_id', errors)

    def test_create_product_unauthorized(self):
        """Неавторизованный -> 403 (DRF с IsAuthenticated)"""
        self.client.force_authenticate(user=None)
        data = {'title': 'test'}
        response = self.client.post(self.products_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ========== RETRIEVE ==========
    def test_retrieve_product_detail(self):
        """Получение товара по ID"""
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=self.user_id,
            category=self.category,
            title='Test Product',
            status=BaseProductStatus.CREATED
        )
        url = reverse('product-detail', kwargs={'product_id': product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(product.id))
        self.assertEqual(response.data['title'], 'Test Product')
        self.assertIn('category', response.data)
        self.assertEqual(response.data['category']['id'], str(self.category.id))

    def test_retrieve_product_not_found(self):
        """Товар не найден -> 404"""
        url = reverse('product-detail', kwargs={'product_id': uuid.uuid4()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== UPDATE ==========
    def test_update_product_owner(self):
        """Владелец может обновить товар"""
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=self.user_id,
            category=self.category,
            title='Old Title',
            status=BaseProductStatus.CREATED
        )
        url = reverse('product-detail', kwargs={'product_id': product.id})
        data = {'title': 'New Title', 'category_id': str(self.category.id)}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.title, 'New Title')

    def test_update_product_not_owner(self):
        """Чужой товар нельзя обновить -> 403"""
        other_user = User.objects.create_user(username='other', password='123')
        other_user_id = other_user.id
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=other_user_id,
            category=self.category,
            title='Other Title',
            status=BaseProductStatus.CREATED
        )
        url = reverse('product-detail', kwargs={'product_id': product.id})
        data = {'title': 'Hacked Title'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_product_images_and_chars(self):
        """Обновление вложенных изображений и характеристик (замена списков)"""
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=self.user_id,
            category=self.category,
            title='Base'
        )
        # Начальные данные
        Image.objects.create(product=product, url='old.jpg', ordering=0)
        Characteristic.objects.create(product=product, name='old', value='old')
        url = reverse('product-detail', kwargs={'product_id': product.id})

        data = {
            'title': 'Updated',
            'images': [{'url': 'new.jpg', 'ordering': 1}],
            'characteristics': [{'name': 'Brand', 'value': 'Apple'}],
            'category_id': str(self.category.id)
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.title, 'Updated')
        self.assertEqual(product.images.count(), 1)
        self.assertEqual(product.images.first().url, 'new.jpg')
        self.assertEqual(product.characteristics.count(), 1)
        self.assertEqual(product.characteristics.first().name, 'Brand')

    # ========== DELETE ==========
    def test_delete_product_owner(self):
        """Владелец может удалить свой товар"""
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=self.user_id,
            category=self.category,
            title='To delete'
        )
        url = reverse('product-detail', kwargs={'product_id': product.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Product.objects.count(), 0)

    def test_delete_product_not_owner(self):
        """Чужой товар нельзя удалить -> 403"""
        other_user = User.objects.create_user(username='other2', password='123')
        other_user_id = other_user.id
        product = Product.objects.create(
            id=uuid.uuid4(),
            seller_id=other_user_id,
            category=self.category,
            title='Other delete'
        )
        url = reverse('product-detail', kwargs={'product_id': product.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ========== (опционально) тесты на my-products будут добавлены позже ==========