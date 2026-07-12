from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'status', 'is_active', 'expires_at', 'created_by', 'reviewed_by', 'created_at')
    list_filter = ('audience', 'status', 'is_active')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at',)
