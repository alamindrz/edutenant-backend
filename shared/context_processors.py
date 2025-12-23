# shared/context_processors.py - FIXED
"""
Simplified context processor - FIXED VERSION.
NO circular imports, clean dependency handling.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def unified_context(request):
    """Simplified context processor - FIXED."""
    context = {}
    
    try:
        # 1. BASIC CONTEXT
        context.update({
            'DEBUG': settings.DEBUG,
            'BRAND_NAME': 'Edutenant',
            'current_theme': request.session.get('theme', 'light'),
        })
        
        # 2. SCHOOL CONTEXT
        school = getattr(request, 'school', None)
        if school:
            context.update({
                'current_school': school,
                'school_name': school.name,
                'has_school_context': True,
                'school_logo': school.logo.url if school.logo else None,
                'school_primary_color': getattr(school, 'primary_color', '#007bff'),
            })
        else:
            context.update({
                'current_school': None,
                'has_school_context': False,
            })
        
        # 3. USER & NAVIGATION CONTEXT
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # Import HERE to avoid circular imports
                from .navigation import NavigationBuilder
                
                desktop_nav, mobile_nav, user_role, user_profile, current_school = NavigationBuilder.get_navigation(request)
                
                context.update({
                    'desktop_navigation': desktop_nav,
                    'mobile_navigation': mobile_nav,
                    'user_role': user_role,
                    'user_profile': user_profile,
                    'current_school': current_school or school,  # Use navigation school if available
                    'has_school_context': bool(current_school or school),
                })
                
                # Add permission flags using role directly
                if user_role:
                    # Import permission checker safely
                    from .decorators.permissions import PermissionChecker
                    
                    context.update({
                        'user_can_manage_staff': PermissionChecker.has_permission(user_role, 'manage_staff'),
                        'user_can_manage_students': PermissionChecker.has_permission(user_role, 'manage_students'),
                        'user_can_manage_academics': PermissionChecker.has_permission(user_role, 'manage_academics'),
                        'user_can_manage_finances': PermissionChecker.has_permission(user_role, 'manage_finances'),
                        'user_can_manage_attendance': PermissionChecker.has_permission(user_role, 'manage_attendance'),
                        'user_can_manage_admissions': PermissionChecker.has_permission(user_role, 'manage_admissions'),
                    })
                
                # Get pending applications count if user can manage admissions
                if (current_school or school) and user_role and context.get('user_can_manage_admissions'):
                    try:
                        from django.apps import apps
                        Application = apps.get_model('admissions', 'Application')
                        context['pending_applications_count'] = Application.objects.filter(
                            school=(current_school or school),
                            status='pending'
                        ).count()
                    except Exception as e:
                        logger.debug(f"Could not load pending applications: {e}")
                        context['pending_applications_count'] = 0
                
            except ImportError as e:
                logger.warning(f"Navigation import error: {e}")
                context.update({
                    'desktop_navigation': [],
                    'mobile_navigation': [],
                    'user_role': None,
                    'user_profile': None,
                })
            except Exception as e:
                logger.debug(f"Navigation context error: {e}")
                context.update({
                    'desktop_navigation': [],
                    'mobile_navigation': [],
                    'user_role': None,
                    'user_profile': None,
                })
        
        # 4. NOTIFICATIONS FROM MIDDLEWARE
        if hasattr(request, 'notification_count'):
            context['notification_count'] = request.notification_count
        
        # 5. HTMX CONTEXT
        context['is_htmx'] = request.headers.get('HX-Request', '').lower() == 'true'
        
    except Exception as e:
        logger.error(f"Context processor error: {e}", exc_info=True)
        # Provide minimal context
        context = {
            'DEBUG': settings.DEBUG,
            'BRAND_NAME': 'Edutenant',
            'current_theme': 'light',
            'has_school_context': False,
            'desktop_navigation': [],
            'mobile_navigation': [],
            'is_htmx': False,
        }
    
    return context 