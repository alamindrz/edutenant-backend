"""
config/urls.py - CLEAN, ORGANIZED URL STRUCTURE
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # ===== PUBLIC ROUTES (No authentication required) =====
    path('', views.home_view, name='home'),
    path('discover/', views.school_discovery_view, name='school_discovery'),
    
    # Authentication (allauth)
    path('accounts/', include('allauth.urls')),
    
    # ===== AUTHENTICATED ROUTES (Require login) =====
    path('dashboard/', include('users.urls', namespace='dashboard')),


    path('students/', include('students.urls', namespace='students')),
    path('admissions/', include('admissions.urls', namespace='admissions')),
    path('academics/', include('core.urls', namespace='academics')),
    path('billing/', include('billing.urls', namespace='billing')),
    path('attendance/', include('attendance.urls', namespace='attendance')),
    
    # ===== ADMIN =====
    path('admin/', admin.site.urls),
    
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

