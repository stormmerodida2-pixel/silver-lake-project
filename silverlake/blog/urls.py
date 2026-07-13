from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AdminBlogPostViewSet, BlogImageUploadView, PublicBlogPostViewSet

router = DefaultRouter()
router.register('admin/blog', AdminBlogPostViewSet, basename='admin-blog-post')
router.register('blog', PublicBlogPostViewSet, basename='blog-post')

urlpatterns = [
    path('admin/blog/upload-image/', BlogImageUploadView.as_view(), name='admin-blog-upload-image'),
] + router.urls
