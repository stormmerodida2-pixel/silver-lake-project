from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentViewSet,
    mpesa_callback,
    stk_push,
    token_dispute_payment,
    token_payment_detail,
    token_payment_status,
    token_stk_push,
)

router = DefaultRouter()
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = router.urls + [
    path('payments/mpesa/stk-push/', stk_push, name='mpesa-stk-push'),
    path('payments/mpesa/callback/<str:secret>/', mpesa_callback, name='mpesa-callback'),
    path('pay/<uuid:token>/', token_payment_detail, name='token-payment-detail'),
    path('pay/<uuid:token>/stk-push/', token_stk_push, name='token-stk-push'),
    path('pay/<uuid:token>/payments/<int:payment_id>/', token_payment_status, name='token-payment-status'),
    path('pay/<uuid:token>/payments/<int:payment_id>/dispute/', token_dispute_payment, name='token-dispute-payment'),
]
