from django.contrib import admin

from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_published', 'published_at', 'created_by', 'created_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'excerpt', 'body')
    readonly_fields = ('slug', 'published_at', 'created_at', 'updated_at')
