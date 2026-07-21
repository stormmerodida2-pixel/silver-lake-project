from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import CustomerProfile

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    # Optional - whoever shared their code with this new signup. A typo'd/unknown code raises a
    # clear error rather than silently failing, so a customer trying to credit a friend actually
    # finds out if it didn't work instead of assuming it did.
    referral_code = serializers.CharField(max_length=8, required=False, allow_blank=True, write_only=True)

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_referral_code(self, value):
        if not value:
            return value
        if not CustomerProfile.objects.filter(referral_code=value.upper()).exists():
            raise serializers.ValidationError('This referral code was not recognized.')
        return value.upper()

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            is_active=False,
        )
        referred_by = None
        referral_code = validated_data.get('referral_code')
        if referral_code:
            referrer_profile = CustomerProfile.objects.filter(referral_code=referral_code).first()
            if referrer_profile:
                referred_by = referrer_profile.user
        CustomerProfile.objects.create(user=user, phone_number=validated_data['phone_number'], referred_by=referred_by)
        return user


class UserSerializer(serializers.ModelSerializer):
    phone_number = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    is_driver = serializers.SerializerMethodField()
    driver_status = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    referral_code = serializers.SerializerMethodField()
    referral_credit_balance = serializers.SerializerMethodField()
    referral_credit_amount = serializers.SerializerMethodField()
    is_read_only_session = serializers.SerializerMethodField()
    loyalty_tier_name = serializers.SerializerMethodField()
    loyalty_discount_percent = serializers.SerializerMethodField()
    completed_trip_count = serializers.SerializerMethodField()
    next_loyalty_tier_name = serializers.SerializerMethodField()
    trips_to_next_loyalty_tier = serializers.SerializerMethodField()
    two_factor_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number', 'avatar',
            'is_staff', 'is_superuser', 'is_driver', 'driver_status', 'organization_name',
            'referral_code', 'referral_credit_balance', 'referral_credit_amount',
            'is_read_only_session', 'loyalty_tier_name', 'loyalty_discount_percent',
            'completed_trip_count', 'next_loyalty_tier_name', 'trips_to_next_loyalty_tier',
            'two_factor_enabled',
        ]

    def get_phone_number(self, user):
        profile = getattr(user, 'customer_profile', None)
        return profile.phone_number if profile else ''

    def get_referral_code(self, user):
        profile = getattr(user, 'customer_profile', None)
        return profile.referral_code if profile else None

    def get_referral_credit_balance(self, user):
        from .services import get_available_credit_balance
        return get_available_credit_balance(user)

    def get_referral_credit_amount(self, user):
        # The admin-configurable amount a referrer currently earns per confirmed referral - see
        # ReferralSettings. Included here (rather than requiring a separate request) so the
        # ProfileView referral card can display the real, current promo amount instead of a
        # hardcoded figure that would go stale the moment an admin changes it.
        from .models import ReferralSettings
        return ReferralSettings.get_amount()

    def get_loyalty_tier_name(self, user):
        from .services import get_loyalty_tier
        tier = get_loyalty_tier(user)
        return tier.name if tier else None

    def get_loyalty_discount_percent(self, user):
        from .services import get_loyalty_tier
        tier = get_loyalty_tier(user)
        return tier.discount_percent if tier else Decimal('0')

    def get_completed_trip_count(self, user):
        from .services import get_completed_trip_count
        return get_completed_trip_count(user)

    def get_next_loyalty_tier_name(self, user):
        from .services import get_next_loyalty_tier
        tier = get_next_loyalty_tier(user)
        return tier.name if tier else None

    def get_trips_to_next_loyalty_tier(self, user):
        # For a "3 more trips to Gold" progress display - None once there's no higher tier left.
        from .services import get_completed_trip_count, get_next_loyalty_tier
        next_tier = get_next_loyalty_tier(user)
        if not next_tier:
            return None
        return next_tier.min_completed_trips - get_completed_trip_count(user)

    def get_two_factor_enabled(self, user):
        settings_obj = getattr(user, 'two_factor_settings', None)
        return bool(settings_obj and settings_obj.is_enabled)

    def get_is_read_only_session(self, user):
        # True only for a superadmin's read-only driver-impersonation session (see
        # AdminUserViewSet.impersonate / drivers.permissions.IsDriverUser) - lets
        # ImpersonationBanner.vue show that clearly, and the driver portal itself could use this
        # later to grey out actions instead of just letting them 403.
        request = self.context.get('request')
        token = getattr(request, 'auth', None) if request else None
        return bool(token and token.get('read_only'))

    def get_avatar(self, user):
        profile = getattr(user, 'customer_profile', None)
        if not (profile and profile.avatar):
            return None
        request = self.context.get('request')
        url = profile.avatar.url
        return request.build_absolute_uri(url) if request else url

    def get_is_driver(self, user):
        # Portal access requires an active driver profile - a suspended driver loses it,
        # same as the IsDriverUser permission check on the backend.
        driver = getattr(user, 'driver_profile', None)
        return bool(driver and driver.is_active)

    def get_driver_status(self, user):
        # For UI purposes beyond portal access (e.g. hiding "Become a Driver" once you already
        # have a driver profile, whether active or suspended) - None means no driver profile at all.
        driver = getattr(user, 'driver_profile', None)
        if not driver:
            return None
        return 'active' if driver.is_active else 'suspended'

    def get_organization_name(self, user):
        # None for a genuine SilverLake platform account - see core.models.StaffOrganization.
        # Lets the admin frontend tell a real superadmin apart from a FleetPartner's own
        # org-admin, who's also is_superuser=True but scoped to just their own organization.
        staff_org = getattr(user, 'staff_organization', None)
        return staff_org.organization.name if staff_org else None


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Lets a customer edit their own name and phone number. Deliberately doesn't include email -
    it doubles as the login username with no re-verification flow for changing it, so that stays
    out of scope for a simple self-service profile edit."""

    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number']

    def update(self, instance, validated_data):
        phone_number = validated_data.pop('phone_number', None)
        instance = super().update(instance, validated_data)
        if phone_number is not None:
            CustomerProfile.objects.update_or_create(user=instance, defaults={'phone_number': phone_number})
        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
