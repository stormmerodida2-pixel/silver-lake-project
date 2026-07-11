from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('event', 'message', 'organization', 'created_at')
    list_filter = ('event', 'organization')
    search_fields = ('message',)
    readonly_fields = ('created_at',)
