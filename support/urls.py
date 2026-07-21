from rest_framework.routers import DefaultRouter

from .views import AdminSupportTicketViewSet, MySupportTicketViewSet

router = DefaultRouter()
router.register('support/tickets', MySupportTicketViewSet, basename='support-ticket')
router.register('admin/support', AdminSupportTicketViewSet, basename='admin-support-ticket')

urlpatterns = router.urls
