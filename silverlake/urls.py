"""
URL configuration for silverlake project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('api/', include('accounts.urls')),
    path('api/', include('fleet.urls')),
    path('api/', include('drivers.urls')),
    path('api/', include('bookings.urls')),
    path('api/', include('payments.urls')),
    path('api/', include('reviews.urls')),
    path('api/', include('announcements.urls')),
    path('api/', include('blog.urls')),
    path('api/', include('notifications.urls')),
    path('api/', include('core.urls')),
]

if settings.DEBUG:
    # Django's built-in admin is a local development convenience only - the real admin surface
    # is the custom Vue dashboard at /admin in the frontend, which enforces the two-tier
    # permission system, the audit log, and safeguards (e.g. cash-payout verification) that this
    # raw admin's own ModelAdmin actions don't consistently respect. Never expose it in
    # production - a superuser here could bypass those checks entirely.
    urlpatterns = [path('admin/', admin.site.urls)] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
