from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ActivateAccountView,
    ChangePasswordView,
    LoginView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/activate/<str:uid>/<str:token>/', ActivateAccountView.as_view(), name='auth-activate'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
]
