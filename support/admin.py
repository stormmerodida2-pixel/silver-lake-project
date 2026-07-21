from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'category', 'status', 'user', 'booking', 'created_at')
    list_filter = ('category', 'status')
    search_fields = ('subject', 'description', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
