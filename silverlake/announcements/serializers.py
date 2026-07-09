from rest_framework import serializers

from .models import Announcement


class AdminAnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'title', 'body', 'audience', 'is_active', 'created_by_name', 'created_at']
        read_only_fields = ['created_at']

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.get_full_name() or obj.created_by.email


class MyAnnouncementSerializer(serializers.ModelSerializer):
    """The subset of fields relevant to the person reading it, not managing it - no
    is_active/created_by, since a user only ever sees active announcements meant for them."""

    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'title', 'body', 'audience', 'created_at', 'is_read']

    def get_is_read(self, obj):
        request = self.context['request']
        # Relies on the view prefetching read_by, so this reuses the cached list instead of
        # firing a query per announcement.
        return any(user.id == request.user.id for user in obj.read_by.all())
