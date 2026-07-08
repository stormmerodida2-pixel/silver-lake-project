from django.contrib import admin, messages

from core.audit import log_admin_action

from .models import DriverPayout, Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('booking', 'method', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('method', 'status')
    search_fields = ('mpesa_receipt_number', 'card_transaction_ref', 'phone_number')


@admin.register(DriverPayout)
class DriverPayoutAdmin(admin.ModelAdmin):
    list_display = ('driver', 'booking', 'amount', 'is_paid', 'paid_at', 'created_at')
    list_filter = ('is_paid',)
    search_fields = ('driver__full_name', 'payout_reference')
    autocomplete_fields = ('driver', 'booking')
    readonly_fields = ('booking', 'driver', 'amount', 'created_at')
    actions = ['mark_as_paid']

    @admin.action(description='Mark selected payouts as paid')
    def mark_as_paid(self, request, queryset):
        count = 0
        skipped = 0
        for payout in queryset.filter(is_paid=False):
            # Same rule as AdminDriverPayoutViewSet.mark_paid - a payout sourced from a
            # self-reported cash payment must be explicitly verified first, or this becomes
            # the one place that fabricated cash claim could still sail through to a real payout.
            if payout.needs_verification and not payout.is_verified:
                skipped += 1
                continue
            payout.mark_paid()
            log_admin_action(request, 'payout.mark_paid', payout, detail='via Django admin')
            count += 1
        self.message_user(request, f'{count} payout(s) marked as paid.')
        if skipped:
            self.message_user(
                request,
                f'{skipped} payout(s) skipped - cash-sourced and not yet verified.',
                level=messages.WARNING,
            )
