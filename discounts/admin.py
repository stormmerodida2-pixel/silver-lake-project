from django.contrib import admin

from .models import DiscountCode


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'value', 'is_active', 'is_redeemed', 'redeemed_at', 'created_by', 'created_at')
    list_filter = ('discount_type', 'is_active', 'is_redeemed')
    search_fields = ('code',)
    readonly_fields = ('is_redeemed', 'redeemed_at', 'redeemed_booking', 'created_at')
