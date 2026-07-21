from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .emails import send_activation_email, send_password_reset_email
from .models import CustomerProfile, TwoFactorSettings
from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UpdateProfileSerializer,
    UserSerializer,
)
from .services import blacklist_all_tokens_for_user, request_login_otp, verify_login_otp

User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Accepts either the User's username or their email address in the 'username' field - the
    frontend always labels this field 'Email', but not every account (e.g. superusers created via
    createsuperuser) necessarily has username == email, so resolve email -> username first."""

    def validate(self, attrs):
        identifier = attrs.get(self.username_field)
        if identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                attrs[self.username_field] = user.get_username()

        data = super().validate(attrs)

        # The password's already been checked by this point (super().validate() raises
        # AuthenticationFailed otherwise) - a staff account with 2FA on doesn't get its tokens
        # yet, it gets a one-time code emailed instead (see TwoFactorVerifyView, which is where
        # the real tokens actually get issued). 2FA is staff-only (see TwoFactorEnableView), so a
        # regular customer account is never affected even if this row somehow existed for one.
        two_factor = getattr(self.user, 'two_factor_settings', None)
        if self.user.is_staff and two_factor and two_factor.is_enabled:
            request_login_otp(self.user)
            return {'two_factor_required': True, 'user_id': self.user.id}

        data['user'] = UserSerializer(self.user, context=self.context).data
        return data


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth-login'


class TwoFactorVerifyView(APIView):
    """The second step of logging in once EmailTokenObtainPairSerializer.validate() has replied
    with two_factor_required - takes the code emailed to the account and, if it checks out,
    issues the real access/refresh tokens (identical shape to a normal login response) that
    validate() withheld. AllowAny, same as LoginView itself - the caller isn't authenticated yet,
    that's the whole point of this step."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth-2fa'

    def post(self, request):
        user = User.objects.filter(pk=request.data.get('user_id'), is_staff=True).first()
        if not user:
            return Response({'detail': 'Invalid request.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verify_login_otp(user, request.data.get('code', ''))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user, context={'request': request}).data,
        })


class TwoFactorEnableView(APIView):
    """A staff account opting into 2FA for itself (see Profile -> Security) - no extra
    confirmation needed beyond already being logged in, since turning protection ON is never the
    risky direction (unlike TwoFactorDisableView, which is)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {'detail': 'Two-factor authentication is only available for staff accounts.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        settings_obj, _ = TwoFactorSettings.objects.get_or_create(user=request.user)
        settings_obj.enable()
        return Response({'detail': 'Two-factor authentication enabled.'})


class TwoFactorDisableView(APIView):
    """Requires the account's current password to turn 2FA back off - the same
    already-logged-in session that could enable it could otherwise disable it just as easily
    (e.g. an unattended unlocked laptop), which would defeat the point of having 2FA at all."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.check_password(request.data.get('password', '')):
            return Response({'password': ['Current password is incorrect.']}, status=status.HTTP_400_BAD_REQUEST)
        settings_obj = getattr(request.user, 'two_factor_settings', None)
        if settings_obj:
            settings_obj.disable()
        return Response({'detail': 'Two-factor authentication disabled.'})


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth-register'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_activation_email(user)
        return Response(
            {'detail': 'Account created. Check your email to activate it before logging in.'},
            status=status.HTTP_201_CREATED,
        )


class MeView(generics.RetrieveUpdateAPIView):
    """GET returns the full profile (including read-only is_driver/driver_status); PATCH/PUT
    edits name and phone number via a separate, purely-writable serializer, but the response
    always comes back through UserSerializer so the shape is consistent either way."""

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UpdateProfileSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Re-fetch a clean instance rather than re-serializing self.get_object() - the phone
        # number update goes through a separate CustomerProfile save, but Django caches the
        # reverse customer_profile accessor on the user instance the moment it's first read, so
        # the in-memory object here would still show the old phone number otherwise.
        fresh_user = User.objects.get(pk=request.user.pk)
        return Response(UserSerializer(fresh_user, context=self.get_serializer_context()).data)


class MyAvatarView(APIView):
    """Separate from MeView's name/phone PATCH, same reasoning as gallery images elsewhere in
    this app - a binary upload doesn't belong mixed into a plain JSON field-update endpoint, and
    HTML/multipart forms can't represent "clear this field" the way a POST-to-set /
    DELETE-to-remove pair can."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        avatar = request.FILES.get('avatar')
        if not avatar:
            return Response({'avatar': ['No file provided.']}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        # Django never deletes the previous file just because the field got reassigned - capture
        # it now and only delete it once the new one is validated and saved, so a rejected
        # (e.g. oversized) replacement never destroys the photo that was already there.
        previous_avatar = profile.avatar if profile.avatar else None
        profile.avatar = avatar
        try:
            profile.full_clean(validate_unique=False)
        except DjangoValidationError as exc:
            return Response({'avatar': exc.message_dict.get('avatar', exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        profile.save()
        if previous_avatar:
            previous_avatar.delete(save=False)
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def delete(self, request):
        profile = getattr(request.user, 'customer_profile', None)
        if profile and profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
            profile.save(update_fields=['avatar'])
        return Response(UserSerializer(request.user, context={'request': request}).data)


def _get_user_from_uid(uid):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None


class ActivateAccountView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, uid, token):
        user = _get_user_from_uid(uid)
        if user is None or not default_token_generator.check_token(user, token):
            return Response({'detail': 'Invalid or expired activation link.'}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'detail': 'Account activated. You can now log in.'})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth-password-reset'

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data['email']).first()
        if user is not None:
            send_password_reset_email(user)
        # Always return the same response so we don't leak whether an email is registered.
        return Response({'detail': 'If that email is registered, a reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = _get_user_from_uid(data['uid'])
        if user is None or not default_token_generator.check_token(user, data['token']):
            return Response({'detail': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        blacklist_all_tokens_for_user(user)
        return Response({'detail': 'Password reset. You can now log in.'})


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.check_password(data['old_password']):
            return Response({'old_password': ['Current password is incorrect.']}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(data['new_password'])
        request.user.save(update_fields=['password'])
        blacklist_all_tokens_for_user(request.user)
        return Response({'detail': 'Password changed.'})


class LogoutView(APIView):
    """Blacklists the refresh token behind the current session - without this, "logging out"
    only ever cleared the frontend's own localStorage, and the token itself kept working against
    the API for anyone who still had a copy of it (e.g. from browser history or a shared device)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # Already invalid/expired/blacklisted - logging out is a no-op either way.
        return Response({'detail': 'Logged out.'})
