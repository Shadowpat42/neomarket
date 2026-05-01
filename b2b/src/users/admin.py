from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'company_name', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'company_name')
    list_filter = ('is_active', 'is_staff')