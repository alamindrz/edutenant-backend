# config/urls.py - FIXED VERSION
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # ===== PUBLIC ROUTES =====
    path('', views.home_view, name='home'),
    path('discover/', views.school_discovery_view, name='school_discovery'),
    path('schools/<int:school_id>/', views.school_overview_view, name='school_overview'),
    
    # ===== APPLICATION ROUTES =====
    path('apply/<slug:form_slug>/', views.application_start_view, name='application_start'),
    
    # ===== HEALTH CHECK =====
    path('health/', views.health_check_view, name='health_check'),
    
    # ===== AUTHENTICATION =====
    path('accounts/', include('allauth.urls')),
    
    # ===== SMART DASHBOARD ROUTER =====
    path('dashboard/', views.dashboard_router, name='dashboard_router'),
    
    # ===== APP NAMESPACES (FIXED - Aligned with navigation.py) =====
    path('dashboard/users/', include('users.urls', namespace='users')),
    path('students/', include('students.urls', namespace='students')),
    path('admissions/', include('admissions.urls', namespace='admissions')),
    path('academics/', include('core.urls', namespace='academics')),
    path('billing/', include('billing.urls', namespace='billing')),
    path('attendance/', include('attendance.urls', namespace='attendance')),
    
    # ===== THEME TOGGLE =====
    path('theme/toggle/', views.theme_toggle_view, name='theme_toggle'),
    
    # ===== TEST VIEWS (Remove in production) =====
    path('test/', views.test_urls, name='test_urls'),
    path('debug/', views.debug_context, name='debug_context'),
    
    # ===== ADMIN =====
    path('admin/', admin.site.urls),
]

# Add error handlers
handler404 = 'config.views.handler404'
handler500 = 'config.views.handler500'
handler403 = 'config.views.handler403'
handler400 = 'config.views.handler400'

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 