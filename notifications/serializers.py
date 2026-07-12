from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'event', 'message', 'link_path', 'created_at', 'is_read']

    def get_is_read(self, obj):
        request = self.context['request']
        # Relies on the view prefetching read_by, so this reuses the cached list instead of
        # firing a query per notification (same pattern as MyAnnouncementSerializer.get_is_read).
        return any(user.id == request.user.id for user in obj.read_by.all())
