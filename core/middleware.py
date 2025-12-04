import logging
from django.shortcuts import render
from django.utils import timezone as dj_timezone
from django.http import Http404
from django.conf import settings

from users.models import School
from .exceptions import SchoolManagementException

logger = logging.getLogger(__name__)


# ============================================================
# 0. SESSION VALIDATION MIDDLEWARE (ADD THIS FIRST)
# ============================================================

class SessionValidationMiddleware:
    """
    Validates and repairs session data before other middleware uses it.
    This should be placed RIGHT AFTER SessionMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ Validate session before any other middleware uses it
        self._validate_session(request)
        
        response = self.get_response(request)
        return response

    def _validate_session(self, request):
        """Validate and clean session data safely."""
        if not hasattr(request, 'session'):
            return

        try:
            # Ensure session exists
            if not request.session.session_key:
                request.session.create()
                logger.debug("Created new session")
                return

            # Test if session is accessible by doing a safe read/write
            test_key = '_session_validation'
            original_value = request.session.get(test_key, 0)
            request.session[test_key] = original_value + 1
            
        except Exception as e:
            logger.warning(f"Session validation failed: {e}")
            # If session is corrupted, create a fresh one
            try:
                request.session.flush()
                request.session.create()
                logger.info("Replaced corrupted session with fresh session")
            except Exception as flush_error:
                logger.error(f"Could not flush session: {flush_error}")


# ============================================================
# 1. SCHOOL RESOLUTION MIDDLEWARE (UPDATED)
# ============================================================

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
        request.school = None

        try:
            # ✅ SAFE: Use get() with default to avoid KeyErrors
            request.school = (
                self._resolve_subdomain(request)
                or self._resolve_user(request)
                or self._resolve_session(request)
                or self._dev_fallback(request)
            )
            
            # ✅ Update session with current school if authenticated
            if request.school and hasattr(request, 'user') and request.user.is_authenticated:
                request.session['current_school_id'] = request.school.id
                
        except Exception as e:
            logger.error("School resolution error", exc_info=True)

        return self.get_response(request)

    # ----------- Subdomain Parser -----------

    def _resolve_subdomain(self, request):
        """
        Detects subdomains safely for:
        - Production: school.domain.com
        - Local dev: school.localhost
        """
        try:
            # Skip subdomain resolution for certain paths
            if request.path.startswith(('/admin/', '/static/', '/media/')):
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

    # ----------- User Resolver -----------

    def _resolve_user(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            school = getattr(user, "current_school", None)
            if school:
                logger.debug(f"Resolved school from user: {school.name}")
            return school
        return None

    # ----------- Session Resolver -----------

    def _resolve_session(self, request):
        try:
            # ✅ SAFE: Use get() with default
            school_id = request.session.get("current_school_id")
            if not school_id:
                return None
                
            school = School.objects.filter(id=school_id, is_active=True).first()
            if school:
                logger.debug(f"Resolved school from session: {school.name}")
            return school
            
        except Exception as e:
            logger.debug(f"Session resolution failed: {e}")
            return None

    # ----------- Dev fallback -----------

    def _dev_fallback(self, request):
        user = getattr(request, "user", None)
        if user and user.is_superuser:
            school = School.objects.filter(is_active=True).first()
            if school:
                logger.debug(f"Using dev fallback school: {school.name}")
            return school
        return None


# ============================================================
# 2. TIMEZONE MIDDLEWARE (KEEP AS IS - THIS IS GOOD)
# ============================================================

class TimezoneMiddleware:
    """Applies timezone based on school → user → default."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = "Africa/Lagos"

        school = getattr(request, "school", None)
        user = getattr(request, "user", None)

        if school and getattr(school, "timezone", None):
            tz = school.timezone
        elif user and user.is_authenticated and getattr(user, "timezone", None):
            tz = user.timezone

        try:
            dj_timezone.activate(tz)
            request.timezone = tz
        except Exception:
            dj_timezone.deactivate()
            request.timezone = None

        return self.get_response(request)


# ============================================================
# 3. NOTIFICATION MIDDLEWARE (UPDATED)
# ============================================================

class NotificationMiddleware:
    """Attach unread_notifications and count to request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            try:
                notifications = self.get_unread_notifications(user)
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
        # Placeholder - implement your notification logic here
        return []


# ============================================================
# 4. WHITE-LABEL BRANDING INJECTION (UPDATED)
# ============================================================

class WhiteLabelMiddleware:
    """Injects CSS variables for school branding into HTML pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip for API responses and non-HTML content
        if not self._should_inject_branding(request, response):
            return response

        school = getattr(request, "school", None)
        if not school:
            return response

        return self._inject_branding(response, school)

    def _should_inject_branding(self, request, response):
        """Check if we should inject branding for this request/response."""
        # Skip for API calls, HTMX requests, or non-HTML content
        if (request.headers.get('HX-Request') or 
            request.path.startswith('/api/') or
            not hasattr(response, 'content') or
            response.status_code != 200 or
            'text/html' not in response.get('Content-Type', '')):
            return False
        return True

    def _inject_branding(self, response, school):
        """Safely inject CSS variables into HTML head."""
        try:
            content = response.content.decode('utf-8')
            
            # Only inject if </head> tag exists
            if '</head>' not in content:
                return response

            css_variables = f"""
            <style>
                :root {{
                    --school-primary: {school.primary_color or "#3B82F6"};
                    --school-secondary: {school.secondary_color or "#1E40AF"};
                }}
                .bg-school-primary {{ background-color: {school.primary_color or "#3B82F6"} !important; }}
                .text-school-primary {{ color: {school.primary_color or "#3B82F6"} !important; }}
            </style>
            """

            content = content.replace('</head>', css_variables + '</head>')
            response.content = content.encode('utf-8')
            
            # Update content length
            if 'Content-Length' in response:
                response['Content-Length'] = str(len(response.content))
                
        except Exception as e:
            logger.debug(f"Branding injection failed: {e}")

        return response


# ============================================================
# 5. EXCEPTION HANDLING MIDDLEWARE (KEEP AS IS - THIS IS GOOD)
# ============================================================

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
                "error_message": exception.message if exception.user_friendly else "Operation failed."
            }, status=400)

        # System error
        logger.error(f"System exception: {exception}", exc_info=True)
        template = "core/error_partial.html" if request.headers.get("HX-Request") else "core/error_page.html"

        return render(request, template, {
            "error_message": "System error. Our team has been notified."
        }, status=500)


# ============================================================
# 6. SECURITY HEADERS (UPDATED)
# ============================================================

class SecurityHeadersMiddleware:
    """Adds strict baseline security headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Basic security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Only add CSP for specific pages to avoid breaking HTMX
        if request.path.startswith("/billing/payment/"):
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' js.paystack.co; "
                "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
                "font-src 'self' fonts.gstatic.com; "
                "frame-src js.paystack.co; "
                "connect-src 'self' api.paystack.co;"
            )

        return response


# ============================================================
# 7. REQUEST LOGGING (UPDATED)
# ============================================================

class RequestLoggingMiddleware:
    """Debug-level structured request/response logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip logging for static files and health checks
        if self._should_skip_logging(request):
            return self.get_response(request)

        logger.debug("Request", extra={
            "method": request.method,
            "path": request.path,
            "ip": self._get_client_ip(request),
            "user": getattr(request.user, "id", None) if hasattr(request, 'user') else None,
            "school": getattr(request, "school", None),
        })

        response = self.get_response(request)

        logger.debug("Response", extra={
            "status": response.status_code,
            "path": request.path,
            "user": getattr(request.user, "id", None) if hasattr(request, 'user') else None,
            "school": getattr(request, "school", None),
        })

        return response

    def _should_skip_logging(self, request):
        """Skip logging for noisy requests."""
        skip_paths = ['/static/', '/media/', '/favicon.ico', '/health/']
        return any(request.path.startswith(path) for path in skip_paths)

    def _get_client_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        return xff.split(",")[0] if xff else request.META.get("REMOTE_ADDR", "unknown")