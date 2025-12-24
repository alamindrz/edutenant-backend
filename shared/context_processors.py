# shared/context_processors.py - FIXED & CLEAN
"""
Unified context processor - Clean version with proper error handling.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def unified_context(request):
    """Provide unified context to all templates."""
    context = {}
    
    try:
        # 1. BASIC CONTEXT
        context.update({
            'DEBUG': settings.DEBUG,
            'BRAND_NAME': 'Edutenant',
            'current_theme': request.session.get('theme', 'light'),
            'is_htmx': request.headers.get('HX-Request', '').lower() == 'true',
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
                from .navigation import NavigationBuilder
                
                desktop_nav, mobile_nav, user_role, user_profile, nav_school = NavigationBuilder.get_navigation(request)
                
                # Use navigation school if available, otherwise use middleware school
                current_school = nav_school or school
                
                context.update({
                    'desktop_navigation': desktop_nav,
                    'mobile_navigation': mobile_nav,
                    'user_role': user_role,
                    'user_profile': user_profile,
                    'current_school': current_school,
                    'has_school_context': bool(current_school),
                })
                
                # Add permission flags
                if user_role:
                    try:
                        from .decorators.permissions import PermissionChecker
                        context.update({
                            'user_can_manage_staff': PermissionChecker.has_permission(user_role, 'manage_staff'),
                            'user_can_manage_students': PermissionChecker.has_permission(user_role, 'manage_students'),
                            'user_can_manage_academics': PermissionChecker.has_permission(user_role, 'manage_academics'),
                            'user_can_manage_finances': PermissionChecker.has_permission(user_role, 'manage_finances'),
                            'user_can_manage_attendance': PermissionChecker.has_permission(user_role, 'manage_attendance'),
                            'user_can_manage_admissions': PermissionChecker.has_permission(user_role, 'manage_admissions'),
                        })
                    except ImportError:
                        logger.debug("PermissionChecker import failed, using fallback")
                        context.update({
                            'user_can_manage_staff': _simple_permission_check(user_role, 'manage_staff'),
                            'user_can_manage_students': _simple_permission_check(user_role, 'manage_students'),
                            'user_can_manage_academics': _simple_permission_check(user_role, 'manage_academics'),
                            'user_can_manage_finances': _simple_permission_check(user_role, 'manage_finances'),
                            'user_can_manage_attendance': _simple_permission_check(user_role, 'manage_attendance'),
                            'user_can_manage_admissions': _simple_permission_check(user_role, 'manage_admissions'),
                        })
                
                # Get pending applications count if user can manage admissions
                if current_school and user_role and context.get('user_can_manage_admissions'):
                    try:
                        from django.apps import apps
                        Application = apps.get_model('admissions', 'Application')
                        
                        # Try different field names for school reference
                        if hasattr(Application, 'school'):
                            pending_count = Application.objects.filter(
                                school=current_school,
                                status='pending'
                            ).count()
                        elif hasattr(Application, 'form'):
                            pending_count = Application.objects.filter(
                                form=current_school,
                                status='pending'
                            ).count()
                        else:
                            pending_count = 0
                            
                        context['pending_applications_count'] = pending_count
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
        
    except Exception as e:
        logger.error(f"Context processor error: {e}", exc_info=True)
        # Provide minimal safe context
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


def _simple_permission_check(role, permission):
    """Fallback permission checker when PermissionChecker is not available."""
    if not role:
        return False
    
    # Super users get all permissions
    if getattr(role, 'system_role_type', '') in ['super_admin', 'principal', 'admin']:
        return True
    
    # Check permissions list
    if hasattr(role, 'permissions'):
        if '*' in role.permissions:
            return True
        if permission in role.permissions:
            return True
    
    # Check boolean fields
    permission_map = {
        'manage_staff': 'can_manage_staff',
        'manage_students': 'can_manage_students',
        'manage_academics': 'can_manage_academics',
        'manage_finances': 'can_manage_finances',
        'manage_attendance': 'can_manage_attendance',
    }
    
    if permission in permission_map:
        return getattr(role, permission_map[permission], False)
    
    # Special cases
    if permission == 'manage_admissions':
        return (
            getattr(role, 'can_manage_students', False) or
            getattr(role, 'system_role_type', '') in ['principal', 'admin']
        )
    
    return False