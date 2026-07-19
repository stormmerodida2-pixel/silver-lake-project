from rest_framework import serializers

from .models import DiscountCode, DiscountType


class AdminDiscountCodeSerializer(serializers.ModelSerializer):
    # Declared explicitly (rather than left to ModelSerializer's auto-generation) so it can be
    # left blank for DiscountCode.save() to auto-generate - the model field itself is
    # blank=True, but DRF's auto-built CharField would otherwise still mark it required since
    # UniqueValidator/required inference doesn't account for a save()-time default. Also means
    # DRF's automatic UniqueValidator (only attached to auto-built fields) doesn't apply here,
    # so validate_code below does that check itself, case-insensitively (matching how save()
    # always uppercases before persisting).
    code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    created_by_name = serializers.SerializerMethodField()
    redeemed_booking_id = serializers.SerializerMethodField()

    class Meta:
        model = DiscountCode
        fields = [
            'id', 'code', 'discount_type', 'value', 'is_active', 'is_redeemed', 'redeemed_at',
            'redeemed_booking_id', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['is_redeemed', 'redeemed_at', 'created_at']

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.get_full_name() or obj.created_by.email

    def get_redeemed_booking_id(self, obj):
        return obj.redeemed_booking_id

    def validate_code(self, value):
        if not value:
            return value
        value = value.strip().upper()
        queryset = DiscountCode.objects.filter(code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('A discount code with this code already exists.')
        return value

    def validate_value(self, value):
        if value <= 0:
            raise serializers.ValidationError('Must be greater than zero.')
        return value

    def validate(self, attrs):
        discount_type = attrs.get('discount_type', getattr(self.instance, 'discount_type', DiscountType.FIXED))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        if discount_type == DiscountType.PERCENT and value is not None and value > 100:
            raise serializers.ValidationError({'value': 'A percentage discount cannot exceed 100.'})
        return attrs
