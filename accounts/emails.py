from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.email_utils import send_branded_email


def send_activation_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f'{settings.FRONTEND_URL}/activate/{uid}/{token}'
    send_branded_email(
        subject='Activate your SilverLake Car Rentals account',
        template_name='emails/activation.html',
        context={'first_name': user.first_name, 'activation_url': link},
        recipient_list=[user.email],
    )


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f'{settings.FRONTEND_URL}/reset-password/{uid}/{token}'
    send_branded_email(
        subject='Reset your SilverLake Car Rentals password',
        template_name='emails/password_reset.html',
        context={'first_name': user.first_name, 'reset_url': link},
        recipient_list=[user.email],
    )


def send_login_otp_email(user, code):
    send_branded_email(
        subject=f'Your SilverLake login code: {code}',
        template_name='emails/login_otp.html',
        context={'first_name': user.first_name, 'code': code},
        recipient_list=[user.email],
    )


def send_referral_credit_earned_email(referrer, referred_user, amount):
    if not referrer.email:
        return
    send_branded_email(
        subject='You earned referral credit!',
        template_name='emails/referral_credit_earned.html',
        context={
            'first_name': referrer.first_name,
            'referred_name': referred_user.first_name or referred_user.email,
            'amount': f'{amount:,.0f}',
            'profile_url': f'{settings.FRONTEND_URL}/account/profile',
        },
        recipient_list=[referrer.email],
    )
