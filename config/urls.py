# config/urls.py
"""Edusuite URL Configuration"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [
    # Home and platform routes
    path('', views.home_view, name='home'),
    
    # School discovery and engagement
    path('discover/', views.school_discovery_view, name='school_discovery'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # App routes
    path('users/', include('users.urls', namespace='users')),
    path('core/', include('core.urls', namespace='core')),
    path('students/', include('students.urls', namespace='students')),
    path('billing/', include('billing.urls', namespace='billing')),
    path('admissions/', include('admissions.urls', namespace='admissions')),
    path('attendance/', include('attendance.urls', namespace='attendance')),
    
    # Authentication (Allauth)
    path('accounts/', include('allauth.urls')),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

