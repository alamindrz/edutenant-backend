# users/context_processors.py 
"""
CLEANED CONTEXT PROCESSORS - Using shared architecture
NO circular imports, efficient queries
"""
from django.conf import settings
from django.apps import apps

# SHARED IMPORTS
from shared.constants import PARENT_PHONE_FIELD


def _get_model(model_name, app_label='users'):
    """Helper to get models lazily."""
    return apps.get_model(app_label, model_name)


def navigation_context(request):
    """
    Add navigation context to all templates.
    Efficient queries, uses shared constants.
    """
    context = {}
    
    # Theme preference
    theme = request.COOKIES.get('theme', getattr(settings, 'DEFAULT_THEME', 'light'))
    context['current_theme'] = theme
    
    # Add user context if authenticated
    if request.user.is_authenticated:
        context['user'] = request.user
        
        # Add current school if available
        if hasattr(request, 'school') and request.school:
            context['current_school'] = request.school
            
            try:
                # Get user profile for current school
                Profile = _get_model('Profile')
                profile = Profile.objects.filter(
                    user=request.user, 
                    school=request.school
                ).select_related('role').first()
                
                if profile:
                    context['user_profile'] = profile
                    context['user_role'] = profile.role.name
                    context['user_role_type'] = profile.role.system_role_type
                    
                    # Add quick stats (cached or limited query)
                    from django.core.cache import cache
                    cache_key = f"school_stats_{request.school.id}_{request.user.id}"
                    stats = cache.get(cache_key)
                    
                    if not stats:
                        try:
                            Student = _get_model('Student', 'students')
                            Staff = _get_model('Staff')
                            Class = _get_model('Class', 'core')
                            
                            stats = {
                                'student_count': Student.objects.filter(
                                    school=request.school, 
                                    is_active=True
                                ).count(),
                                'staff_count': Staff.objects.filter(
                                    school=request.school, 
                                    is_active=True
                                ).count(),
                                'class_count': Class.objects.filter(
                                    school=request.school, 
                                    is_active=True
                                ).count(),
                            }
                            
                            # Cache for 5 minutes
                            cache.set(cache_key, stats, 300)
                        except Exception as e:
                            # If any model doesn't exist, use empty stats
                            stats = {
                                'student_count': 0,
                                'staff_count': 0,
                                'class_count': 0,
                            }
                    
                    context['school_stats'] = stats
                    
            except Exception as e:
                # Silently fail - don't break the site if context processor fails
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Navigation context error: {e}")
                context['user_role'] = None
                context['school_stats'] = {}
        else:
            # User is authenticated but no school context
            context['current_school'] = None
            context['school_stats'] = {}
    
    # Add site-wide settings
    context['site_name'] = getattr(settings, 'SITE_NAME', 'Edusuite')
    context['support_email'] = getattr(settings, 'SUPPORT_EMAIL', 'support@edusuite.com')
    context['debug'] = settings.DEBUG
    
    return context


def user_permissions_context(request):
    """
    Add user permissions to context for template checks.
    More efficient than checking permissions in every view.
    """
    context = {}
    
    if request.user.is_authenticated and hasattr(request, 'school'):
        try:
            Profile = _get_model('Profile')
            profile = Profile.objects.filter(
                user=request.user, 
                school=request.school
            ).select_related('role').first()
            
            if profile and profile.role:
                role = profile.role
                context['user_permissions'] = {
                    'can_manage_roles': role.can_manage_roles,
                    'can_manage_staff': role.can_manage_staff,
                    'can_manage_students': role.can_manage_students,
                    'can_manage_academics': role.can_manage_academics,
                    'can_manage_finances': role.can_manage_finances,
                    'can_view_reports': role.can_view_reports,
                    'can_communicate': role.can_communicate,
                    'is_system_role': role.is_system_role,
                    'system_role_type': role.system_role_type,
                }
        except Exception:
            context['user_permissions'] = {}
    
    return context


def feature_flags_context(request):
    """
    Add feature flags to context for enabling/disabling features.
    """
    context = {}
    
    # Example feature flags (could come from database or settings)
    context['feature_flags'] = {
        'enable_payments': getattr(settings, 'ENABLE_PAYMENTS', True),
        'enable_messaging': getattr(settings, 'ENABLE_MESSAGING', True),
        'enable_attendance': getattr(settings, 'ENABLE_ATTENDANCE', True),
        'enable_grading': getattr(settings, 'ENABLE_GRADING', True),
        'enable_parent_portal': getattr(settings, 'ENABLE_PARENT_PORTAL', True),
    }
    
    return context