from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet

router = DefaultRouter()
router.register('admin/notifications', NotificationViewSet, basename='admin-notification')

urlpatterns = router.urls
