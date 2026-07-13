from rest_framework import serializers

from .models import BlogImageUpload, BlogPost
from .sanitize import sanitize_body


class AdminBlogPostSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'excerpt', 'body', 'cover_image',
            'is_published', 'published_at', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['slug', 'published_at', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.get_full_name() or obj.created_by.email

    def validate_body(self, value):
        return sanitize_body(value)


class PublicBlogPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        # No created_by/created_by_name - public byline is a hardcoded "SilverLake Car Rentals
        # Team" string in the frontend template, never a real staff name.
        fields = ['id', 'title', 'slug', 'excerpt', 'body', 'cover_image', 'published_at']


class BlogImageUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogImageUpload
        fields = ['id', 'image']
