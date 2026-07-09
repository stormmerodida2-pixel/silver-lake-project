from rest_framework import serializers

from .models import Announcement


class AdminAnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    # DRF's auto-generated BooleanField doesn't inherit the model's default=True - by design,
    # DRF treats a missing checkbox-style field as False to mimic real HTML forms (see
    # BooleanField.get_value()/default_empty_html), which only kicks in for form/multipart
    # requests, not JSON ones. The frontend always sends JSON so it never hit this in practice,
    # but any form-encoded client (curl -F, Postman form-data) silently created inactive
    # announcements. Declaring the default explicitly makes it correct for every encoding.
    is_active = serializers.BooleanField(default=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'body', 'audience', 'is_active', 'status', 'review_note',
            'created_by_name', 'reviewed_by_name', 'created_at',
        ]
        # status/review_note/reviewed_by are only ever set by the view (perform_create forces
        # them for staff proposals; approve/reject set them for a superadmin's decision) - never
        # directly writable through create/update, so a staff submitter can't just mark their
        # own proposal approved.
        read_only_fields = ['created_at', 'status', 'review_note']

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.get_full_name() or obj.created_by.email

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by_id:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.email


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
