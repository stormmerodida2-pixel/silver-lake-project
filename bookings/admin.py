from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'customer_name', 'vehicle', 'service_type', 'driver',
        'start_date', 'end_date', 'status', 'total_amount',
        'platform_fee_amount', 'driver_payout_amount', 'created_at',
    )
    list_filter = ('status', 'service_type')
    search_fields = ('customer_name', 'customer_phone', 'customer_email')
    autocomplete_fields = ('vehicle', 'driver')
    readonly_fields = (
        'total_amount', 'amount_paid', 'balance_due', 'deposit_amount',
        'platform_fee_amount', 'driver_payout_amount', 'created_at', 'updated_at',
    )

    @admin.display(description='Platform fee')
    def platform_fee_amount(self, obj):
        return obj.platform_fee_amount

    @admin.display(description='Driver payout')
    def driver_payout_amount(self, obj):
        return obj.driver_payout_amount
