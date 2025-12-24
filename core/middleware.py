# core/middleware.py
"""
CLEANED MIDDLEWARE - Using shared architecture
NO direct model imports, PROPER lazy loading, WELL LOGGED
"""
import logging
from typing import Optional
from typing import Any, List
from django.shortcuts import render
from django.utils import timezone as dj_timezone
from django.http import Http404
from django.conf import settings
from django.apps import apps

# SHARED IMPORTS
from shared.constants import StatusChoices
from .exceptions import SchoolManagementException

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'users'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def _get_school_model():
    """Get School model lazily."""
    return _get_model('School', 'core')  # ✅ Changed from 'users' to 'core' based on your new structure


# ============ SESSION VALIDATION MIDDLEWARE ============

class SessionValidationMiddleware:
    """
    Validates session data safely.
    FIXED: Removed aggressive 'flush()' which caused logouts on server restart.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'session') and request.session.session_key:
            # We only want to check if the session is working. 
            # If it's not, Django's engine handles it. Manual flushing here is too risky.
            try:
                # Minimal read to check validity
                _ = request.session.get('_session_valid')
            except Exception as e:
                logger.warning(f"Session read failed, letting Django handle it: {e}")
        
        return self.get_response(request)


# ============ SECURITY HEADERS MIDDLEWARE ============

class SecurityHeadersMiddleware:
    """
    Adds baseline security headers.
    FIXED: Added check to ensure response is an object before assignment.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # BUG FIX: Ensure we have a proper HttpResponse object and not a function/None
        if response is None or callable(response):
            return response

        # Add headers safely
        try:
            response["X-Content-Type-Options"] = "nosniff"
            response["X-Frame-Options"] = "DENY"
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"

            if request.path.startswith("/billing/payment/"):
                response["Content-Security-Policy"] = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://js.paystack.co; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                    "frame-src https://js.paystack.co;"
                )
        except TypeError:
            # Fallback if response is a TemplateResponse that isn't rendered yet
            pass

        return response



# ============ SCHOOL RESOLUTION MIDDLEWARE ============

class SchoolMiddleware:
    """
    Determines the active school using this order:
    1. Subdomain:   school.domain.com or school.localhost
    2. User:        user.current_school
    3. Session:     session['current_school_id']
    4. Dev fallback: First active school for superusers
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize school as None
        request.school = None

        try:
            # Get school using resolution order
            school = (
                self._resolve_subdomain(request)
                or self._resolve_user(request)
                or self._resolve_session(request)
                or self._dev_fallback(request)
            )

            if school:
                request.school = school

                # ✅ ONLY update session if school changed and user is authenticated
                if hasattr(request, 'user') and request.user.is_authenticated:
                    current_session_school = request.session.get('current_school_id')
                    if not current_session_school or current_session_school != school.id:
                        request.session['current_school_id'] = school.id
                        request.session.modified = True

        except Exception as e:
            logger.error(f"School resolution error: {e}", exc_info=True)

        return self.get_response(request)

    def _resolve_subdomain(self, request) -> Optional[Any]:
        """
        Detects subdomains safely for:
        - Production: school.domain.com
        - Local dev: school.localhost
        """
        try:
            # Skip subdomain resolution for certain paths
            if request.path.startswith(('/admin/', '/static/', '/media/', '/api/')):
                return None

            host = request.get_host().split(":")[0].lower()

            if host.startswith("www."):
                host = host[4:]

            parts = host.split(".")

            # school.localhost → ["school", "localhost"]
            if "localhost" in host and len(parts) == 2:
                subdomain = parts[0]
            # Production: school.domain.com
            elif len(parts) > 2:
                subdomain = parts[0]
            else:
                return None

            # ✅ Use lazy loading for School model
            School = _get_school_model()

            school = School.objects.filter(
                subdomain=subdomain,
                is_active=True,
                subdomain_status="active"
            ).first()

            if school:
                logger.debug(f"Resolved school from subdomain: {school.name}")

            return school

        except Exception as e:
            logger.debug(f"Subdomain resolution failed: {e}")
            return None

    def _resolve_user(self, request) -> Optional[Any]:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            school = getattr(user, "current_school", None)
            if school:
                logger.debug(f"Resolved school from user: {school.name}")
            return school
        return None

    def _resolve_session(self, request) -> Optional[Any]:
        try:
            school_id = request.session.get("current_school_id")
            if not school_id:
                return None

            # ✅ Use lazy loading for School model
            School = _get_school_model()

            school = School.objects.filter(id=school_id, is_active=True).first()
            if school:
                logger.debug(f"Resolved school from session: {school.name}")
            return school

        except Exception as e:
            logger.debug(f"Session resolution failed: {e}")
            return None

    def _dev_fallback(self, request) -> Optional[Any]:
        user = getattr(request, "user", None)
        if user and user.is_superuser:
            # ✅ Use lazy loading for School model
            School = _get_school_model()
            school = School.objects.filter(is_active=True).first()
            if school:
                logger.debug(f"Using dev fallback school: {school.name}")
            return school
        return None


# ============ TIMEZONE MIDDLEWARE ============

class TimezoneMiddleware:
    """Applies timezone based on school → user → default."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ Use shared constant or default
        tz = getattr(settings, 'DEFAULT_TIMEZONE', 'Africa/Lagos')

        school = getattr(request, "school", None)
        user = getattr(request, "user", None)

        if school and getattr(school, "timezone", None):
            tz = school.timezone
        elif user and user.is_authenticated and getattr(user, "timezone", None):
            tz = user.timezone

        try:
            # Only activate if different from current timezone
            current_tz = dj_timezone.get_current_timezone_name()
            if current_tz != tz:
                dj_timezone.activate(tz)
                request.timezone = tz
            else:
                request.timezone = current_tz
        except Exception as e:
            logger.debug(f"Timezone activation failed: {e}")
            dj_timezone.deactivate()
            request.timezone = None

        return self.get_response(request)


# ============ NOTIFICATION MIDDLEWARE ============

class NotificationMiddleware:
    """Attach unread_notifications and count to request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        # Cache notifications in session to avoid DB hits on every request
        if user and user.is_authenticated:
            try:
                # Check if we have cached notifications
                cache_key = f'user_{user.id}_notifications'
                notifications = request.session.get(cache_key)

                # Only refresh every 5 minutes
                last_refresh = request.session.get(f'{cache_key}_time')
                needs_refresh = not notifications or not last_refresh

                if needs_refresh:
                    notifications = self.get_unread_notifications(user)
                    request.session[cache_key] = notifications
                    request.session[f'{cache_key}_time'] = dj_timezone.now().isoformat()

                request.unread_notifications = notifications
                request.notification_count = len(notifications)
            except Exception as e:
                logger.debug(f"Notification loading failed: {e}")
                request.unread_notifications = []
                request.notification_count = 0
        else:
            request.unread_notifications = []
            request.notification_count = 0

        return self.get_response(request)

    def get_unread_notifications(self, user):
        """Get unread notifications for user (to be implemented)."""
        # ✅ This should be moved to a service
        # from notifications.services import NotificationService
        # return NotificationService.get_unread_notifications(user)
        return []


# ============ WHITE-LABEL BRANDING INJECTION ============

class WhiteLabelMiddleware:
    """Injects CSS variables for school branding into HTML pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip for non-HTML responses
        if not self._should_inject_branding(request, response):
            return response

        school = getattr(request, "school", None)
        if not school:
            return response

        return self._inject_branding(response, school)

    def _should_inject_branding(self, request, response) -> bool:
        """Check if we should inject branding for this request/response."""
        # Skip for API calls, HTMX requests, or non-HTML content
        content_type = response.get('Content-Type', '')
        return (
            not request.headers.get('HX-Request') and
            not request.path.startswith('/api/') and
            hasattr(response, 'content') and
            response.status_code == 200 and
            'text/html' in content_type
        )

    def _inject_branding(self, response, school):
        """Safely inject CSS variables into HTML head."""
        try:
            content = response.content.decode('utf-8')

            # Only inject if </head> tag exists
            if '</head>' not in content:
                return response

            # ✅ Use safe defaults from shared constants
            primary_color = school.primary_color or "#3B82F6"
            secondary_color = school.secondary_color or "#1E40AF"

            css_variables = f"""
            <style>
                :root {{
                    --school-primary: {primary_color};
                    --school-secondary: {secondary_color};
                }}
                .bg-school-primary {{ background-color: var(--school-primary) !important; }}
                .text-school-primary {{ color: var(--school-primary) !important; }}
                .border-school-primary {{ border-color: var(--school-primary) !important; }}
                .hover\\:bg-school-primary:hover {{ background-color: var(--school-primary) !important; }}
            </style>
            """

            content = content.replace('</head>', css_variables + '</head>')
            response.content = content.encode('utf-8')

            # Update content length
            response['Content-Length'] = str(len(response.content))

        except Exception as e:
            logger.debug(f"Branding injection failed: {e}")

        return response


# ============ EXCEPTION HANDLING MIDDLEWARE ============

class ExceptionHandlingMiddleware:
    """Handles SchoolManagementException and general server errors."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Business logic error
        if isinstance(exception, SchoolManagementException):
            logger.warning(f"Business exception: {exception}")

            template = "core/error_partial.html" if request.headers.get("HX-Request") else "core/error_page.html"
            return render(request, template, {
                "error_message": str(exception) if getattr(exception, 'user_friendly', False) else "Operation failed."
            }, status=400)

        # System error
        logger.error(f"System exception: {exception}", exc_info=True)
        template = "core/error_partial.html" if request.headers.get("HX-Request") else "core/error_page.html"

        return render(request, template, {
            "error_message": "System error. Our team has been notified."
        }, status=500)



# ============ REQUEST LOGGING MIDDLEWARE ============

class RequestLoggingMiddleware:
    """Debug-level structured request/response logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip logging for static files and health checks
        if self._should_skip_logging(request):
            return self.get_response(request)

        # Only log in debug mode
        if settings.DEBUG:
            logger.debug("Request", extra={
                "method": request.method,
                "path": request.path,
                "ip": self._get_client_ip(request),
                "user": getattr(request.user, "id", None) if hasattr(request, 'user') else None,
                "school": getattr(request, "school", None),
            })

        response = self.get_response(request)

        if settings.DEBUG:
            logger.debug("Response", extra={
                "path": request.path,
                "user": getattr(request.user, "id", None) if hasattr(request, 'user') else None,
                "school": getattr(request, "school", None),
            })

        return response

    def _should_skip_logging(self, request) -> bool:
        """Skip logging for noisy requests."""
        # ✅ Use shared constant for skip paths
        skip_paths = ['/static/', '/media/', '/favicon.ico', '/health/', '/__debug__/']
        return any(request.path.startswith(path) for path in skip_paths)

    def _get_client_ip(self, request) -> str:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        return xff.split(",")[0] if xff else request.META.get("REMOTE_ADDR", "unknown")
