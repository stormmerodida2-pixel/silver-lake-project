from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AdminAnnouncementViewSet, MarkAnnouncementReadView, MyAnnouncementsView

router = DefaultRouter()
router.register('admin/announcements', AdminAnnouncementViewSet, basename='admin-announcement')

urlpatterns = [
    path('announcements/mine/', MyAnnouncementsView.as_view(), name='announcements-mine'),
    path('announcements/<int:pk>/mark-read/', MarkAnnouncementReadView.as_view(), name='announcement-mark-read'),
] + router.urls
