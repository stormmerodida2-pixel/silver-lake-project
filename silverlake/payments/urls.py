from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet, mpesa_callback, stk_push

router = DefaultRouter()
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = router.urls + [
    path('payments/mpesa/stk-push/', stk_push, name='mpesa-stk-push'),
    path('payments/mpesa/callback/', mpesa_callback, name='mpesa-callback'),
]
