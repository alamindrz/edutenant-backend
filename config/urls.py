# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from . import views

# -------------------------------------------------------------------
# URL CONFIGURATION
# -------------------------------------------------------------------

urlpatterns = [
    # ----------------------------------------------------------------
    # Public routes
    # ----------------------------------------------------------------
    path("", views.home_view, name="home"),
    path("discover/", views.school_discovery_view, name="school_feed"),
    path(
        "schools/<int:school_id>/",
        views.school_overview_view,
        name="school_overview",
    ),

    # ----------------------------------------------------------------
    # Applications
    # ----------------------------------------------------------------
    path(
        "apply/<slug:form_slug>/",
        views.application_start_view,
        name="application_start",
    ),

    # ----------------------------------------------------------------
    # Health & diagnostics
    # ----------------------------------------------------------------
    path("health/", views.health_check_view, name="health_check"),

    # ----------------------------------------------------------------
    # Authentication (django-allauth)
    # ----------------------------------------------------------------
    path("accounts/", include("allauth.urls")),

    # ----------------------------------------------------------------


    # ----------------------------------------------------------------
    # Application namespaces
    # ----------------------------------------------------------------
    path("dashboard/users/", include(("users.urls", "users"), namespace="users")),
    path("students/", include(("students.urls", "students"), namespace="students")),
    path("admissions/", include(("admissions.urls", "admissions"), namespace="admissions")),
    path("academics/", include(("core.urls", "academics"), namespace="academics")),
    path("billing/", include(("billing.urls", "billing"), namespace="billing")),
    path("attendance/", include(("attendance.urls", "attendance"), namespace="attendance")),

    # ----------------------------------------------------------------
    # UI utilities
    # ----------------------------------------------------------------
    path("theme/toggle/", views.theme_toggle_view, name="theme_toggle"),

    # ----------------------------------------------------------------
    # Debug / test (remove in production)
    # ----------------------------------------------------------------
    path("test/", views.test_urls, name="test_urls"),
    path("debug/", views.debug_context, name="debug_context"),

    # ----------------------------------------------------------------
    # Admin
    # ----------------------------------------------------------------
    path("admin/", admin.site.urls),
]

# -------------------------------------------------------------------
# Error handlers
# -------------------------------------------------------------------

handler400 = "config.views.handler400"
handler403 = "config.views.handler403"
handler404 = "config.views.handler404"
handler500 = "config.views.handler500"

# -------------------------------------------------------------------
# Static & media (development only)
# -------------------------------------------------------------------

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT,
    )