# config/views.py - FIXED
"""
Smart view controllers with proper error handling and URL routing.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.apps import apps
import json
from django.utils import timezone

from core.models import School


# ============================================================================
# PUBLIC VIEWS
# ============================================================================

def home_view(request):
    """Public landing page with smart routing."""
    # Authenticated users with school -> dashboard
    if request.user.is_authenticated:
        if hasattr(request, 'school') and request.school:
            return redirect('users:dashboard')
        return redirect('users:school_list')

    # Public landing page
    try:
        # REMOVED select_related('logo') - logo is not a relationship field
        featured_schools = School.objects.filter(
            is_active=True,
            application_form_enabled=True,
        ).order_by('-created_at')[:6]
    except Exception:
        featured_schools = []

    context = {
        'featured_schools': featured_schools,
        'total_schools': School.objects.filter(is_active=True).count(),
        'page_title': 'Edutenant - School Management Platform',
        'show_hero': True,
    }

    return render(request, 'home.html', context)


def school_discovery_view(request):
    """Public school discovery with filtering."""
    schools = School.objects.filter(is_active=True, application_form_enabled=True)

    # Apply filters
    search = request.GET.get('q', '')
    school_type = request.GET.get('type', '')
    sort = request.GET.get('sort', 'newest')

    if search:
        schools = schools.filter(
            Q(name__icontains=search) |
            Q(address__icontains=search) |
            Q(description__icontains=search)
        )

    if school_type:
        schools = schools.filter(school_type=school_type)

    # Sorting
    if sort == 'name':
        schools = schools.order_by('name')
    else:  # newest
        schools = schools.order_by('-created_at')

    # Pagination
    paginator = Paginator(schools, 12)
    page = request.GET.get('page', 1)

    try:
        schools_page = paginator.page(page)
    except:
        schools_page = paginator.page(1)

    # Stats for cards
    hiring_schools = School.objects.filter(is_active=True).count()
    open_positions = 0

    context = {
        'schools': schools_page,
        'search_query': search,
        'school_type': school_type,
        'sort': sort,
        'hiring_schools_count': hiring_schools,
        'total_open_positions': open_positions,
        'new_this_week': 0,
        'page_title': 'Discover Schools',
    }

    return render(request, 'school_discovery.html', context)


def school_overview_view(request, school_id):
    """Public school profile page."""
    school = get_object_or_404(School, id=school_id, is_active=True)

    context = {
        'school': school,
        'page_title': school.name,
        'page_subtitle': f'{school.get_school_type_display()} • {school.city or school.address}',
    }

    return render(request, 'schools/overview.html', context)


# ============================================================================
# APPLICATION VIEWS
# ============================================================================

def application_start_view(request, form_slug):
    """Start an application to a school."""
    # Try to find school by slug or subdomain
    try:
        school = School.objects.get(
            Q(slug=form_slug) | Q(subdomain=form_slug),
            is_active=True,
            application_form_enabled=True
        )
    except School.DoesNotExist:
        messages.error(request, "Application form not found.")
        return redirect('school_discovery')

    # Check if user is already a member
    if request.user.is_authenticated:
        try:
            Profile = apps.get_model('users', 'Profile')
            if Profile.objects.filter(user=request.user, school=school).exists():
                messages.info(request, f"You're already a member of {school.name}.")
                return redirect('users:dashboard')
        except:
            pass

    context = {
        'school': school,
        'page_title': f'Apply to {school.name}',
    }

    return render(request, 'admissions/public_application_start.html', context)


# ============================================================================
# THEME & UTILITY VIEWS
# ============================================================================

def theme_toggle_view(request):
    """Toggle theme preference."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            theme = data.get('theme', 'light')
            request.session['theme'] = theme
            return JsonResponse({'success': True, 'theme': theme})
        except:
            return JsonResponse({'success': False}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def dashboard_router(request):
    """Smart router to appropriate dashboard."""
    if hasattr(request, 'school') and request.school:
        return redirect('users:dashboard')
    return redirect('users:school_list')


# ============================================================================
# HEALTH & STATUS
# ============================================================================

def health_check_view(request):
    """System health check endpoint."""
    from django.db import connection
    from django.db.utils import OperationalError

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = True
    except OperationalError:
        db_status = False

    status_code = 200 if db_status else 503

    return JsonResponse({
        'status': 'healthy' if db_status else 'unhealthy',
        'database': 'connected' if db_status else 'disconnected',
        'timestamp': timezone.now().isoformat(),
    }, status=status_code)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

def handler404(request, exception):
    context = {
        'page_title': 'Page Not Found',
        'error_code': 404,
        'error_message': 'The page you are looking for does not exist.',
    }
    return render(request, 'errors/404.html', context, status=404)


def handler500(request):
    context = {
        'page_title': 'Server Error',
        'error_code': 500,
        'error_message': 'Something went wrong on our end.',
    }
    return render(request, 'errors/500.html', context, status=500)


def handler403(request, exception):
    context = {
        'page_title': 'Access Denied',
        'error_code': 403,
        'error_message': 'You do not have permission to access this page.',
    }
    return render(request, 'errors/403.html', context, status=403)


def handler400(request, exception):
    context = {
        'page_title': 'Bad Request',
        'error_code': 400,
        'error_message': 'Your request could not be processed.',
    }
    return render(request, 'errors/400.html', context, status=400)


# ============================================================================
# DEBUG & TEST VIEWS (Remove in production)
# ============================================================================

@login_required
def test_urls(request):
    """Test URL resolution."""
    from django.urls import reverse, NoReverseMatch

    test_cases = [
        ('users:dashboard', 'User Dashboard'),
        ('users:school_list', 'School List'),
        ('users:profile', 'User Profile'),
        ('students:student_list', 'Student List'),
        ('admissions:dashboard', 'Admissions Dashboard'),
        ('home', 'Home'),
        ('school_discovery', 'School Discovery'),
        ('account_login', 'Login'),
        ('account_logout', 'Logout'),
    ]

    results = []
    for url_name, description in test_cases:
        try:
            url = reverse(url_name)
            results.append({'name': url_name, 'description': description, 'url': url, 'status': '✓'})
        except NoReverseMatch as e:
            results.append({'name': url_name, 'description': description, 'url': str(e), 'status': '✗'})

    context = {
        'results': results,
        'page_title': 'URL Test',
    }

    return render(request, 'test_urls.html', context)


@login_required
def debug_context(request):
    """View all available context variables."""
    context_data = {}

    # Basic request info
    context_data['request'] = {
        'path': request.path,
        'method': request.method,
        'user': str(request.user),
        'user_authenticated': request.user.is_authenticated,
        'is_htmx': request.headers.get('HX-Request') == 'true',
    }

    # School context
    if hasattr(request, 'school'):
        context_data['school'] = {
            'name': request.school.name if request.school else None,
            'id': request.school.id if request.school else None,
        }

    # Session data (safe)
    if hasattr(request, 'session'):
        session_keys = list(request.session.keys())
        safe_keys = [k for k in session_keys if not k.startswith('_')]
        context_data['session'] = {
            'keys': safe_keys[:10],
            'session_key': request.session.session_key[:20] + '...' if request.session.session_key else None,
        }

    # User context from middleware
    if hasattr(request, 'notification_count'):
        context_data['notifications'] = {
            'count': request.notification_count,
            'has_unread': request.notification_count > 0,
        }

    context = {
        'debug_data': context_data,
        'page_title': 'Debug Context',
    }

    return render(request, 'debug_context.html', context)
