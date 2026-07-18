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

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number', 'avatar',
            'is_staff', 'is_superuser', 'is_driver', 'driver_status', 'organization_name',
            'referral_code', 'referral_credit_balance',
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
