from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import CustomerProfile

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def create(self, validated_data):
        first_name, _, last_name = validated_data['full_name'].partition(' ')
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            first_name=first_name,
            last_name=last_name,
            password=validated_data['password'],
            is_active=False,
        )
        CustomerProfile.objects.create(user=user, phone_number=validated_data['phone_number'])
        return user


class UserSerializer(serializers.ModelSerializer):
    phone_number = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    is_driver = serializers.SerializerMethodField()
    driver_status = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number', 'avatar',
            'is_staff', 'is_superuser', 'is_driver', 'driver_status', 'organization_name',
        ]

    def get_phone_number(self, user):
        profile = getattr(user, 'customer_profile', None)
        return profile.phone_number if profile else ''

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
