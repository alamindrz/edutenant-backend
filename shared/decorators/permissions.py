"""
Unified decorators for role-based access control and school context management.

This module provides decorators for:
1. School context management
2. Role-based permission checking
3. HTMX request handling
4. Resource access restriction

All decorators include comprehensive logging and error handling.
"""

import logging
from functools import wraps
from typing import Optional, Callable, Any

from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.apps import apps
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_user_profile(user: 'User', school: 'School') -> Optional['Profile']:
    """
    Get user's profile for a specific school.
    
    Args:
        user: Django User instance
        school: School instance
    
    Returns:
        Profile instance or None if not found
    """
    try:
        Profile = apps.get_model('users', 'Profile')
        profile = Profile.objects.select_related('role').get(
            user=user, 
            school=school,
            is_active=True
        )
        logger.debug(f"Found profile for user {user.id} in school {school.id}")
        return profile
    except Profile.DoesNotExist:
        logger.warning(
            f"No active profile found for user {user.id} in school {school.id} "
            f"(school: {school.name})"
        )
        return None
    except Exception as e:
        logger.error(
            f"Error retrieving profile for user {user.id} in school {school.id}: {str(e)}",
            exc_info=True
        )
        return None


def _get_current_school(request: HttpRequest) -> Optional['School']:
    """
    Get current school from request object with multiple fallback strategies.
    
    Priority:
    1. School from middleware (request.school)
    2. User's current_school attribute
    3. First active school from user's profiles
    4. School ID from URL parameters or session
    
    Args:
        request: HttpRequest object
    
    Returns:
        School instance or None
    """
    # Priority 1: School from middleware
    if hasattr(request, 'school') and request.school:
        logger.debug(f"Using school from middleware: {request.school.name}")
        return request.school
    
    # Priority 2: User's current_school attribute (if authenticated)
    if request.user.is_authenticated and hasattr(request.user, 'current_school'):
        school = request.user.current_school
        if school:
            logger.debug(f"Using user's current_school: {school.name}")
            return school
    
    # Priority 3: First active school from user's profiles
    if request.user.is_authenticated:
        try:
            Profile = apps.get_model('users', 'Profile')
            profile = Profile.objects.filter(
                user=request.user, 
                is_active=True
            ).select_related('school').first()
            
            if profile and profile.school:
                logger.debug(f"Using school from first active profile: {profile.school.name}")
                return profile.school
        except Exception as e:
            logger.error(f"Error getting school from profiles: {str(e)}", exc_info=True)
    
    # Priority 4: School ID from URL parameters
    school_id = request.GET.get('school_id') or request.POST.get('school_id')
    if not school_id and request.resolver_match:
        # Try to extract from URL kwargs
        kwargs = request.resolver_match.kwargs
        school_id = kwargs.get('school_id') or kwargs.get('school_pk')
    
    if school_id:
        try:
            School = apps.get_model('core', 'School')
            school = School.objects.get(id=school_id, is_active=True)
            logger.debug(f"Using school from URL parameter: {school.name}")
            return school
        except School.DoesNotExist:
            logger.warning(f"School with ID {school_id} not found or inactive")
    
    # Priority 5: School ID from session
    school_id = request.session.get('current_school_id')
    if school_id:
        try:
            School = apps.get_model('core', 'School')
            school = School.objects.get(id=school_id, is_active=True)
            logger.debug(f"Using school from session: {school.name}")
            return school
        except School.DoesNotExist:
            logger.warning(f"School with ID {school_id} from session not found")
    
    logger.warning("No school context found for request")
    return None


def _has_permission(user: 'User', school: 'School', permission: str) -> bool:
    """
    Check if user has specific permission for a school.
    
    Args:
        user: Django User instance
        school: School instance
        permission: Permission string (e.g., 'manage_staff', 'view_reports')
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    # Superusers bypass all permission checks
    if getattr(user, 'is_superuser', False):
        logger.debug(f"Superuser {user.id} bypasses permission check for {permission}")
        return True
    
    # Check if user and school are provided
    if not user or not school:
        logger.warning(f"Missing user or school for permission check: user={user}, school={school}")
        return False
    
    # Get user's profile for this school
    profile = _get_user_profile(user, school)
    if not profile:
        logger.warning(f"No profile found for permission check: user={user.id}, school={school.id}")
        return False
    
    # Check if profile has a role
    if not profile.role:
        logger.warning(f"No role assigned to profile {profile.id}")
        return False
    
    # System admins have all permissions
    if getattr(profile.role, 'system_role_type', '') == 'super_admin':
        logger.debug(f"System admin bypasses permission check for {permission}")
        return True
    
    # Check specific permission
    permissions = getattr(profile.role, 'permissions', [])
    if not isinstance(permissions, (list, set, tuple)):
        logger.error(f"Invalid permissions format for role {profile.role.id}: {type(permissions)}")
        return False
    
    # Check for wildcard permission or specific permission
    has_permission = '*' in permissions or permission in permissions
    
    if has_permission:
        logger.debug(
            f"Permission granted: user={user.id}, school={school.id}, "
            f"permission={permission}, role={profile.role.name}"
        )
    else:
        logger.debug(
            f"Permission denied: user={user.id}, school={school.id}, "
            f"permission={permission}, role={profile.role.name}, "
            f"available_permissions={list(permissions)}"
        )
    
    return has_permission


def _is_htmx_request(request: HttpRequest) -> bool:
    """
    Check if request is an HTMX request.
    
    Args:
        request: HttpRequest object
    
    Returns:
        bool: True if HTMX request
    """
    is_htmx = request.headers.get('HX-Request', '').lower() == 'true'
    if is_htmx:
        logger.debug(f"HTMX request detected: {request.path}")
    return is_htmx


def _handle_permission_denied(
    request: HttpRequest, 
    permission: str,
    is_htmx: bool = False
) -> HttpResponse:
    """
    Handle permission denied scenario consistently.
    
    Args:
        request: HttpRequest object
        permission: Required permission that was denied
        is_htmx: Whether this is an HTMX request
    
    Returns:
        HttpResponse appropriate for the request type
    """
    error_message = f"You don't have permission to {permission.replace('_', ' ')}"
    logger.warning(
        f"Permission denied for user {request.user.id} on {request.path}: {error_message}"
    )
    
    if is_htmx:
        # Return JSON response for HTMX requests
        return JsonResponse({
            'error': 'Permission Denied',
            'message': error_message,
            'redirect': settings.LOGIN_URL if not request.user.is_authenticated else '/'
        }, status=403)
    else:
        # For regular requests, show message and redirect
        if not request.user.is_authenticated:
            messages.error(request, "Please login to access this page.")
            return redirect(settings.LOGIN_URL)
        
        messages.error(request, error_message)
        return redirect('dashboard')


# ============================================================================
# CORE DECORATORS
# ============================================================================

def require_school_context(
    redirect_to: str = 'school_selection',
    allow_public: bool = True
) -> Callable:
    """
    Decorator to ensure school context is available in the request.
    
    Args:
        redirect_to: View name to redirect to if no school context
        allow_public: Allow access to public paths without school context
    
    Returns:
        Decorated view function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            # Skip school context check for public paths if allowed
            if allow_public:
                public_paths = [
                    '/', '/accounts/', '/auth/', '/login/', '/register/',
                    '/schools/onboarding/', '/invitations/accept/',
                    '/api/', '/webhook/', '/health/'
                ]
                if any(request.path.startswith(path) for path in public_paths):
                    logger.debug(f"Skipping school context check for public path: {request.path}")
                    return view_func(request, *args, **kwargs)
            
            # Get current school
            school = _get_current_school(request)
            
            if not school:
                logger.warning(f"No school context for user {request.user.id} on path {request.path}")
                
                if _is_htmx_request(request):
                    return JsonResponse({
                        'error': 'School Context Required',
                        'message': 'Please select a school to continue.',
                        'redirect': redirect_to
                    }, status=400)
                
                messages.warning(request, "Please select a school to continue.")
                return redirect(redirect_to)
            
            # Add school to request for consistency
            if not hasattr(request, 'school') or not request.school:
                request.school = school
                logger.debug(f"Added school {school.name} to request context")
            
            # Add school to template context if not already present
            if hasattr(request, 'resolver_match'):
                # This ensures school is available in all templates
                if not hasattr(request, 'template_context'):
                    request.template_context = {}
                request.template_context['school'] = school
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


def require_permission(
    permission: str,
    redirect_to: str = 'dashboard',
    require_school: bool = True
) -> Callable:
    """
    Decorator to require specific permission for a view.
    
    Args:
        permission: Required permission string
        redirect_to: View name to redirect to if permission denied
        require_school: Whether school context is required
    
    Returns:
        Decorated view function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            is_htmx = _is_htmx_request(request)
            
            # Get school context if required
            school = None
            if require_school:
                school = _get_current_school(request)
                if not school:
                    logger.warning(f"No school context for permission check: {permission}")
                    return _handle_permission_denied(request, permission, is_htmx)
            else:
                # For system-level permissions, try to get any school
                school = _get_current_school(request)
            
            # Check permission
            if not _has_permission(request.user, school, permission):
                return _handle_permission_denied(request, permission, is_htmx)
            
            logger.info(
                f"Permission granted for user {request.user.id} "
                f"on {request.path} with permission {permission}"
            )
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


def require_role(
    role_type: str,
    redirect_to: str = 'dashboard'
) -> Callable:
    """
    Decorator to require specific system role type.
    
    Args:
        role_type: Required system role type (e.g., 'principal', 'teacher')
        redirect_to: View name to redirect to if role doesn't match
    
    Returns:
        Decorated view function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @require_school_context()
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            is_htmx = _is_htmx_request(request)
            
            if not school:
                return _handle_permission_denied(request, f"be a {role_type}", is_htmx)
            
            # Get user's profile
            profile = _get_user_profile(request.user, school)
            if not profile or not profile.role:
                logger.warning(
                    f"No role found for user {request.user.id} in school {school.id}"
                )
                return _handle_permission_denied(request, f"be a {role_type}", is_htmx)
            
            # Check role type
            user_role_type = getattr(profile.role, 'system_role_type', '')
            if user_role_type != role_type:
                logger.warning(
                    f"Role mismatch: user {request.user.id} has role {user_role_type}, "
                    f"required {role_type}"
                )
                
                if is_htmx:
                    return JsonResponse({
                        'error': 'Role Required',
                        'message': f'This action requires {role_type.replace("_", " ")} role.',
                        'user_role': user_role_type
                    }, status=403)
                
                messages.error(
                    request, 
                    f"This page is only accessible to {role_type.replace('_', ' ').title()}s."
                )
                return redirect(redirect_to)
            
            logger.debug(
                f"Role check passed: user {request.user.id} has role {role_type}"
            )
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# ============================================================================
# PERMISSION-SPECIFIC SHORTCUT DECORATORS
# ============================================================================

def require_manage_staff(view_func: Callable) -> Callable:
    """Shortcut for 'manage_staff' permission."""
    return require_permission('manage_staff')(view_func)


def require_manage_students(view_func: Callable) -> Callable:
    """Shortcut for 'manage_students' permission."""
    return require_permission('manage_students')(view_func)


def require_manage_academics(view_func: Callable) -> Callable:
    """Shortcut for 'manage_academics' permission."""
    return require_permission('manage_academics')(view_func)


def require_manage_finances(view_func: Callable) -> Callable:
    """Shortcut for 'manage_finances' permission."""
    return require_permission('manage_finances')(view_func)


def require_manage_roles(view_func: Callable) -> Callable:
    """Shortcut for 'manage_roles' permission."""
    return require_permission('manage_roles')(view_func)


def require_view_reports(view_func: Callable) -> Callable:
    """Shortcut for 'view_reports' permission."""
    return require_permission('view_reports')(view_func)


def require_communicate(view_func: Callable) -> Callable:
    """Shortcut for 'communicate' permission."""
    return require_permission('communicate')(view_func)


def require_manage_attendance(view_func: Callable) -> Callable:
    """Shortcut for 'manage_attendance' permission."""
    return require_permission('manage_attendance')(view_func)


# ============================================================================
# PERMISSION-SPECIFIC SHORTCUT DECORATORS
# ============================================================================

def require_manage_staff(view_func: Callable) -> Callable:
    """Shortcut for 'manage_staff' permission."""
    return require_permission('manage_staff')(view_func)


def require_manage_students(view_func: Callable) -> Callable:
    """Shortcut for 'manage_students' permission."""
    return require_permission('manage_students')(view_func)


def require_manage_academics(view_func: Callable) -> Callable:
    """Shortcut for 'manage_academics' permission."""
    return require_permission('manage_academics')(view_func)


def require_manage_finances(view_func: Callable) -> Callable:
    """Shortcut for 'manage_finances' permission."""
    return require_permission('manage_finances')(view_func)


def require_manage_roles(view_func: Callable) -> Callable:
    """Shortcut for 'manage_roles' permission."""
    return require_permission('manage_roles')(view_func)


def require_view_reports(view_func: Callable) -> Callable:
    """Shortcut for 'view_reports' permission."""
    return require_permission('view_reports')(view_func)


def require_communicate(view_func: Callable) -> Callable:
    """Shortcut for 'communicate' permission."""
    return require_permission('communicate')(view_func)


def require_manage_attendance(view_func: Callable) -> Callable:
    """Shortcut for 'manage_attendance' permission."""
    return require_permission('manage_attendance')(view_func)


# ============================================================================
# ROLE-SPECIFIC SHORTCUT DECORATORS
# ============================================================================

def require_principal(view_func: Callable) -> Callable:
    """Shortcut for 'principal' role."""
    return require_role('principal')(view_func)


def require_teacher(view_func: Callable) -> Callable:
    """Shortcut for 'teacher' role."""
    return require_role('teacher')(view_func)


def require_admin_staff(view_func: Callable) -> Callable:
    """Shortcut for 'admin_staff' role."""
    return require_role('admin_staff')(view_func)


def require_head_teacher(view_func: Callable) -> Callable:
    """Shortcut for 'head_teacher' role."""
    return require_role('head_teacher')(view_func)


def require_department_head(view_func: Callable) -> Callable:
    """Shortcut for 'department_head' role."""
    return require_role('department_head')(view_func)


# ============================================================================
# RESOURCE ACCESS CONTROL DECORATORS
# ============================================================================

def restrict_to_school(
    model_app: str = None,
    model_name: str = None,
    school_field: str = 'school',
    id_param: str = 'pk'
) -> Callable:
    """
    Decorator to ensure users only access resources from their current school.
    
    Args:
        model_app: App label containing the model (e.g., 'students')
        model_name: Model name (e.g., 'Student')
        school_field: Name of the foreign key field to School
        id_param: URL parameter name containing the object ID
    
    Returns:
        Decorated view function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @require_school_context()
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            if not school:
                messages.error(request, "No school context available.")
                return redirect('dashboard')
            
            # Get object ID from kwargs
            object_id = kwargs.get(id_param)
            if not object_id:
                logger.error(f"No {id_param} found in URL parameters")
                raise PermissionDenied("Resource identifier required.")
            
            # Determine model
            model = None
            if model_app and model_name:
                try:
                    model = apps.get_model(model_app, model_name)
                except LookupError as e:
                    logger.error(f"Model {model_app}.{model_name} not found: {e}")
                    raise PermissionDenied("Invalid resource type.")
            else:
                # Try to infer from URL pattern
                # This is a simplified version - adjust based on your URL patterns
                view_name = request.resolver_match.view_name
                # Extract model name from view name (e.g., 'students:detail' -> 'students')
                if ':' in view_name:
                    app_name = view_name.split(':')[0]
                    try:
                        # Try common model names
                        for possible_model in ['Student', 'Parent', 'Staff', 'Class']:
                            try:
                                model = apps.get_model(app_name, possible_model)
                                break
                            except LookupError:
                                continue
                    except Exception as e:
                        logger.error(f"Could not infer model from view {view_name}: {e}")
            
            if not model:
                logger.error(f"Could not determine model for view {request.path}")
                raise PermissionDenied("Cannot verify resource ownership.")
            
            # Get object and verify it belongs to user's school
            try:
                obj = get_object_or_404(model, id=object_id)
                
                # Check if object belongs to user's school
                obj_school = getattr(obj, school_field, None)
                if not obj_school:
                    logger.error(f"Object {model.__name__}.{object_id} has no {school_field} field")
                    raise PermissionDenied("Resource school association missing.")
                
                if obj_school != school:
                    logger.warning(
                        f"School mismatch: user {request.user.id} from school {school.id} "
                        f"tried to access {model.__name__}.{object_id} from school {obj_school.id}"
                    )
                    raise PermissionDenied("You can only access resources from your school.")
                
                logger.debug(
                    f"School access granted: user {request.user.id} "
                    f"accessing {model.__name__}.{object_id}"
                )
                
                # Add object to kwargs for convenience
                kwargs['object'] = obj
                
            except model.DoesNotExist:
                logger.warning(f"{model.__name__} with ID {object_id} not found")
                raise PermissionDenied("Resource not found.")
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# ============================================================================
# HTMX-SPECIFIC DECORATORS
# ============================================================================

def htmx_required(view_func: Callable) -> Callable:
    """
    Decorator to require HTMX request headers.
    
    Returns:
        Decorated view function that returns 400 for non-HTMX requests
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _is_htmx_request(request):
            logger.warning(f"Non-HTMX request to HTMX-only view: {request.path}")
            return JsonResponse({
                'error': 'HTMX Required',
                'message': 'This endpoint requires HTMX headers.',
                'status': 400
            }, status=400)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def htmx_permission_required(permission: str) -> Callable:
    """
    HTMX-specific permission decorator with JSON responses.
    
    Args:
        permission: Required permission string
    
    Returns:
        Decorated view function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @htmx_required
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            
            if not _has_permission(request.user, school, permission):
                logger.warning(
                    f"HTMX permission denied: user {request.user.id} "
                    f"on {request.path} for permission {permission}"
                )
                return JsonResponse({
                    'error': 'Permission Denied',
                    'message': f'Requires {permission.replace("_", " ")} permission.',
                    'status': 403
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# ============================================================================
# COMPOSITE DECORATORS
# ============================================================================

def staff_only(view_func: Callable) -> Callable:
    """
    Composite decorator for staff-only areas.
    Requires login, school context, and any staff permission.
    """
    @wraps(view_func)
    @login_required
    @require_school_context()
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        school = _get_current_school(request)
        is_htmx = _is_htmx_request(request)
        
        # Superusers are always staff
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Get user's profile
        profile = _get_user_profile(request.user, school)
        if not profile:
            logger.warning(f"No profile for user {request.user.id} in staff-only area")
            return _handle_permission_denied(request, "access staff area", is_htmx)
        
        # Check if user has any staff permission
        permissions = getattr(profile.role, 'permissions', [])
        if not permissions:
            logger.warning(f"No permissions for user {request.user.id} in staff-only area")
            return _handle_permission_denied(request, "access staff area", is_htmx)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def admin_only(view_func: Callable) -> Callable:
    """
    Composite decorator for admin-only areas.
    Requires either manage_staff or manage_roles permission.
    """
    @wraps(view_func)
    @login_required
    @require_school_context()
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        school = _get_current_school(request)
        is_htmx = _is_htmx_request(request)
        
        # Check for admin permissions
        has_admin_access = (
            _has_permission(request.user, school, 'manage_staff') or
            _has_permission(request.user, school, 'manage_roles')
        )
        
        if not has_admin_access:
            logger.warning(
                f"Admin access denied for user {request.user.id} "
                f"on school {school.id if school else 'None'}"
            )
            return _handle_permission_denied(request, "access admin area", is_htmx)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view
    
# ============================================================================
# UTILITY FUNCTIONS FOR USE IN VIEWS
# ============================================================================

def check_permission(user: 'User', school: 'School', permission: str) -> bool:
    """
    Utility function to check permissions in views.
    
    Example:
        if check_permission(request.user, request.school, 'manage_staff'):
            # Do admin action
    
    Args:
        user: Django User instance
        school: School instance
        permission: Permission string to check
    
    Returns:
        bool: True if user has permission
    """
    return _has_permission(user, school, permission)


def get_user_role(user: 'User', school: 'School') -> Optional['Role']:
    """
    Get user's role for a specific school.
    
    Args:
        user: Django User instance
        school: School instance
    
    Returns:
        Role instance or None
    """
    profile = _get_user_profile(user, school)
    return profile.role if profile else None


def is_principal(user: 'User', school: 'School') -> bool:
    """Check if user is principal in school."""
    role = get_user_role(user, school)
    return role and getattr(role, 'system_role_type', '') == 'principal'


def is_teacher(user: 'User', school: 'School') -> bool:
    """Check if user is teacher in school."""
    role = get_user_role(user, school)
    return role and getattr(role, 'system_role_type', '') == 'teacher'


def is_admin_staff(user: 'User', school: 'School') -> bool:
    """Check if user is admin staff in school."""
    role = get_user_role(user, school)
    return role and getattr(role, 'system_role_type', '') == 'admin_staff'


# ============================================================================
# DECORATOR REGISTRY (for debugging and documentation)
# ============================================================================

def get_decorator_registry() -> dict:
    """
    Returns a dictionary of all available decorators.
    Useful for documentation and debugging.
    
    Returns:
        dict: Mapping of decorator names to functions
    """
    return {
        # Core decorators
        'require_school_context': require_school_context,
        'require_permission': require_permission,
        'require_role': require_role,
        
        # Permission shortcuts
        'require_manage_staff': require_manage_staff,
        'require_manage_students': require_manage_students,
        'require_manage_academics': require_manage_academics,
        'require_manage_finances': require_manage_finances,
        'require_manage_roles': require_manage_roles,
        'require_view_reports': require_view_reports,
        'require_communicate': require_communicate,
        'require_manage_attendance': require_manage_attendance,
        
        # Role shortcuts
        'require_principal': require_principal,
        'require_teacher': require_teacher,
        'require_admin_staff': require_admin_staff,
        'require_head_teacher': require_head_teacher,
        'require_department_head': require_department_head,
        
        # Resource control
        'restrict_to_school': restrict_to_school,
        
        # HTMX decorators
        'htmx_required': htmx_required,
        'htmx_permission_required': htmx_permission_required,
        
        # Composite decorators
        'staff_only': staff_only,
        'admin_only': admin_only,
    }


# ============================================================================
# EXPORT ALL DECORATORS
# ============================================================================

__all__ = [
    # Core decorators
    'require_school_context',
    'require_permission', 
    'require_role',
    
    # Permission shortcuts
    'require_manage_staff',
    'require_manage_students',
    'require_manage_academics',
    'require_manage_finances',
    'require_manage_roles',
    'require_view_reports',
    'require_communicate',
    'require_manage_attendance',
    
    # Role shortcuts
    'require_principal',
    'require_teacher',
    'require_admin_staff',
    'require_head_teacher',
    'require_department_head',
    
    # Resource control
    'restrict_to_school',
    
    # HTMX decorators
    'htmx_required',
    'htmx_permission_required',
    
    # Composite decorators
    'staff_only',
    'admin_only',
    
    # Utility functions
    'check_permission',
    'get_user_role',
    'is_principal',
    'is_teacher',
    'is_admin_staff',
    'get_decorator_registry',
]

