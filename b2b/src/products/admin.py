from django.contrib import admin
from .models import Product, Category, Image, Characteristic

class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'seller_id', 'category', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'category')
    search_fields = ('title', 'description', 'seller_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Основное', {
            'fields': ('id', 'title', 'description', 'seller_id', 'category', 'status')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name',)
    raw_id_fields = ('parent',)  # удобно для выбора родительской категории

class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'url', 'ordering')
    list_filter = ('product',)
    search_fields = ('url',)

class CharacteristicAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'name', 'value')
    list_filter = ('product',)
    search_fields = ('name', 'value')

# Регистрируем модели в админке
admin.site.register(Product, ProductAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Image, ImageAdmin)
admin.site.register(Characteristic, CharacteristicAdmin)