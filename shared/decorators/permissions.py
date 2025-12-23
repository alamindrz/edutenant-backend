# shared/decorators/permissions.py
"""
UNIFIED PERMISSION SYSTEM
==========================

Core permission checking and decorators for role-based access control.
All permission logic flows through PermissionChecker for consistency.
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
# 1. PERMISSION CHECKER - SINGLE SOURCE OF TRUTH
# ============================================================================

class PermissionChecker:
    """Centralized permission validation used across entire system."""
    
    @staticmethod
    def has_permission(role, permission: str) -> bool:
        """
        Check if a role has a specific permission.
        
        Hierarchy:
        1. Superusers and system admins → All permissions
        2. Wildcard (*) in permissions list → All permissions
        3. Explicit permission in permissions list → Specific permission
        4. Boolean field on role → Legacy support
        5. System role type inference → Automatic permissions
        """
        if not role:
            return False
        
        # 1. SUPER USERS & SYSTEM ADMINS
        if getattr(role, 'system_role_type', '') in ['super_admin', 'principal', 'admin']:
            return True
        
        # 2. WILDCARD PERMISSION
        if hasattr(role, 'permissions') and '*' in role.permissions:
            return True
        
        # 3. EXPLICIT PERMISSION IN LIST
        if hasattr(role, 'permissions') and permission in role.permissions:
            return True
        
        # 4. BOOLEAN FIELDS (LEGACY SUPPORT)
        BOOLEAN_PERMISSION_MAP = {
            'manage_academics': 'can_manage_academics',
            'manage_students': 'can_manage_students',
            'manage_staff': 'can_manage_staff',
            'manage_roles': 'can_manage_roles',
            'manage_finances': 'can_manage_finances',
            'view_reports': 'can_view_reports',
            'communicate': 'can_communicate',
            'manage_attendance': 'can_manage_attendance',
        }
        
        if permission in BOOLEAN_PERMISSION_MAP:
            if getattr(role, BOOLEAN_PERMISSION_MAP[permission], False):
                return True
        
        # 5. SYSTEM ROLE INFERENCES
        SYSTEM_ROLE_PERMISSIONS = {
            'manage_admissions': ['principal', 'admin'],
            'view_students': ['teacher', 'parent', 'principal', 'admin'],
            'manage_attendance': ['teacher', 'principal', 'admin'],
        }
        
        if permission in SYSTEM_ROLE_PERMISSIONS:
            system_role = getattr(role, 'system_role_type', '')
            if system_role in SYSTEM_ROLE_PERMISSIONS[permission]:
                return True
        
        return False
    
    @staticmethod
    def get_user_role(user, school) -> Optional[Any]:
        """Get user's role for a specific school."""
        if not user or not user.is_authenticated or not school:
            return None
        
        try:
            Profile = apps.get_model('users', 'Profile')
            profile = Profile.objects.select_related('role').filter(
                user=user,
                school=school
            ).first()
            
            return profile.role if profile else None
        except Exception:
            return None


# ============================================================================
# 2. HELPER FUNCTIONS
# ============================================================================

def _get_user_profile(user: 'User', school: 'School') -> Optional['Profile']:
    """Get user's profile for a specific school."""
    if not user or not user.is_authenticated or not school:
        return None
    
    try:
        Profile = apps.get_model('users', 'Profile')
        
        # Try with is_active filter first
        try:
            profile = Profile.objects.select_related('role').get(
                user=user,
                school=school,
                is_active=True
            )
        except Exception:
            # Fallback without is_active
            profile = Profile.objects.select_related('role').filter(
                user=user,
                school=school
            ).first()
        
        return profile
    except Exception:
        return None


def _get_current_school(request: HttpRequest) -> Optional['School']:
    """Get current school from request."""
    # Priority 1: School from middleware
    if hasattr(request, 'school') and request.school:
        return request.school
    
    # Priority 2: User's current_school
    if request.user.is_authenticated and hasattr(request.user, 'current_school'):
        if request.user.current_school:
            return request.user.current_school
    
    # Priority 3: School from session
    school_id = request.session.get('current_school_id')
    if school_id:
        try:
            School = apps.get_model('core', 'School')
            return School.objects.filter(id=school_id, is_active=True).first()
        except Exception:
            pass
    
    return None


def _is_htmx_request(request: HttpRequest) -> bool:
    """Check if request is an HTMX request."""
    return request.headers.get('HX-Request', '').lower() == 'true'


def _handle_permission_denied(
    request: HttpRequest, 
    permission: str,
    is_htmx: bool = False
) -> HttpResponse:
    """Handle permission denied consistently."""
    error_message = f"You don't have permission to {permission.replace('_', ' ')}"
    
    if is_htmx:
        return JsonResponse({
            'success': False,
            'error': 'Permission Denied',
            'message': error_message,
            'redirect': settings.LOGIN_URL if not request.user.is_authenticated else '/'
        }, status=403)
    else:
        if not request.user.is_authenticated:
            messages.error(request, "Please login to access this page.")
            return redirect(settings.LOGIN_URL + f'?next={request.path}')
        
        messages.error(request, error_message)
        return redirect('users:dashboard')


# ============================================================================
# 3. CORE DECORATORS
# ============================================================================

def require_school_context(
    redirect_to: str = 'users:school_list',
    allow_public: bool = True
) -> Callable:
    """Decorator to ensure school context is available."""
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            # Skip school check for public paths if allowed
            if allow_public:
                public_paths = ['/', '/accounts/', '/auth/', '/login/', '/register/',
                               '/schools/onboarding/', '/invitations/accept/',
                               '/api/', '/webhook/', '/health/']
                if any(request.path.startswith(path) for path in public_paths):
                    return view_func(request, *args, **kwargs)
            
            # Get school context
            school = _get_current_school(request)
            
            if not school:
                logger.warning(f"No school context for user {request.user.id} on {request.path}")
                
                if _is_htmx_request(request):
                    return JsonResponse({
                        'error': 'School Context Required',
                        'message': 'Please select a school to continue.',
                        'redirect': redirect_to
                    }, status=400)
                
                messages.warning(request, "Please select a school to continue.")
                return redirect(redirect_to)
            
            # Add school to request if not already present
            if not hasattr(request, 'school') or not request.school:
                request.school = school
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


def require_permission(
    permission: str,
    redirect_to: str = 'users:dashboard',
    require_school: bool = True
) -> Callable:
    """Decorator to require specific permission for a view."""
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
                    return _handle_permission_denied(request, permission, is_htmx)
            
            # Get user's role
            role = PermissionChecker.get_user_role(request.user, school)
            
            # Check permission
            if not PermissionChecker.has_permission(role, permission):
                return _handle_permission_denied(request, permission, is_htmx)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


def require_role(
    role_type: str,
    redirect_to: str = 'users:dashboard'
) -> Callable:
    """Decorator to require specific system role type."""
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @require_school_context()
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            is_htmx = _is_htmx_request(request)
            
            if not school:
                return _handle_permission_denied(request, f"be a {role_type}", is_htmx)
            
            # Get user's role
            role = PermissionChecker.get_user_role(request.user, school)
            
            # Check role type
            if not role or getattr(role, 'system_role_type', '') != role_type:
                logger.warning(
                    f"Role mismatch: user {request.user.id} has role {getattr(role, 'system_role_type', 'None')}, "
                    f"required {role_type}"
                )
                
                if is_htmx:
                    return JsonResponse({
                        'error': 'Role Required',
                        'message': f'This action requires {role_type.replace("_", " ")} role.',
                        'user_role': getattr(role, 'system_role_type', 'None')
                    }, status=403)
                
                messages.error(
                    request, 
                    f"This page is only accessible to {role_type.replace('_', ' ').title()}s."
                )
                return redirect(redirect_to)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# ============================================================================
# 4. PERMISSION-SPECIFIC SHORTCUT DECORATORS
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


def require_manage_admissions(view_func: Callable) -> Callable:
    """Shortcut for 'manage_admissions' permission."""
    return require_permission('manage_admissions')(view_func)


# ============================================================================
# 5. ROLE-SPECIFIC SHORTCUT DECORATORS
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


def require_parent(view_func: Callable) -> Callable:
    """Shortcut for 'parent' role."""
    return require_role('parent')(view_func)


# ============================================================================
# 6. RESOURCE ACCESS CONTROL DECORATORS
# ============================================================================

def restrict_to_school(
    model_app: str,
    model_name: str,
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
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @require_school_context()
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            if not school:
                messages.error(request, "No school context available.")
                return redirect('users:dashboard')
            
            # Get object ID
            object_id = kwargs.get(id_param)
            if not object_id:
                logger.error(f"No {id_param} found in URL parameters")
                raise PermissionDenied("Resource identifier required.")
            
            # Get model
            try:
                model = apps.get_model(model_app, model_name)
            except LookupError as e:
                logger.error(f"Model {model_app}.{model_name} not found: {e}")
                raise PermissionDenied("Invalid resource type.")
            
            # Get object and verify school ownership
            try:
                obj = get_object_or_404(model, id=object_id)
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
                
                # Add object to kwargs for convenience
                kwargs['object'] = obj
                
            except model.DoesNotExist:
                logger.warning(f"{model.__name__} with ID {object_id} not found")
                raise PermissionDenied("Resource not found.")
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator


# ============================================================================
# 7. HTMX-SPECIFIC DECORATORS
# ============================================================================

def htmx_required(view_func: Callable) -> Callable:
    """Decorator to require HTMX request headers."""
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
    """HTMX-specific permission decorator with JSON responses."""
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        @htmx_required
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            school = _get_current_school(request)
            role = PermissionChecker.get_user_role(request.user, school)
            
            if not PermissionChecker.has_permission(role, permission):
                logger.warning(
                    f"HTMX permission denied: user {request.user.id} "
                    f"for permission {permission}"
                )
                return JsonResponse({
                    'success': False,
                    'error': 'Permission Denied',
                    'message': f'Requires {permission.replace("_", " ")} permission.',
                    'status': 403
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    
    return decorator

# ============================================================================
# 8. COMPOSITE DECORATORS
# ============================================================================

def staff_only(view_func: Callable) -> Callable:
    """Composite decorator for staff-only areas."""
    @wraps(view_func)
    @login_required
    @require_school_context()
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        school = _get_current_school(request)
        is_htmx = _is_htmx_request(request)
        
        # Superusers are always staff
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Get user's role
        role = PermissionChecker.get_user_role(request.user, school)
        
        # Check if user has any staff permission
        staff_permissions = [
            'manage_staff', 'manage_students', 'manage_academics',
            'manage_finances', 'manage_roles', 'view_reports',
            'communicate', 'manage_attendance', 'manage_admissions'
        ]
        
        has_staff_access = any(
            PermissionChecker.has_permission(role, perm)
            for perm in staff_permissions
        )
        
        if not has_staff_access:
            return _handle_permission_denied(request, "access staff area", is_htmx)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def admin_only(view_func: Callable) -> Callable:
    """Composite decorator for admin-only areas."""
    @wraps(view_func)
    @login_required
    @require_school_context()
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        school = _get_current_school(request)
        is_htmx = _is_htmx_request(request)
        
        # Get user's role
        role = PermissionChecker.get_user_role(request.user, school)
        
        # Check for admin permissions
        has_admin_access = (
            PermissionChecker.has_permission(role, 'manage_staff') or
            PermissionChecker.has_permission(role, 'manage_roles')
        )
        
        if not has_admin_access:
            return _handle_permission_denied(request, "access admin area", is_htmx)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


# ============================================================================
# 9. UTILITY FUNCTIONS FOR USE IN VIEWS
# ============================================================================

def check_permission(user: 'User', school: 'School', permission: str) -> bool:
    """Utility function to check permissions in views."""
    role = PermissionChecker.get_user_role(user, school)
    return PermissionChecker.has_permission(role, permission)


def get_user_role(user: 'User', school: 'School') -> Optional['Role']:
    """Get user's role for a specific school."""
    return PermissionChecker.get_user_role(user, school)


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


def is_parent(user: 'User', school: 'School') -> bool:
    """Check if user is parent in school."""
    role = get_user_role(user, school)
    return role and getattr(role, 'system_role_type', '') == 'parent'


# ============================================================================
# 10. EXPORT ALL DECORATORS AND FUNCTIONS
# ============================================================================

__all__ = [
    # Permission Checker
    'PermissionChecker',
    
    # Core Decorators
    'require_school_context',
    'require_permission', 
    'require_role',
    
    # Permission Shortcuts
    'require_manage_staff',
    'require_manage_students',
    'require_manage_academics',
    'require_manage_finances',
    'require_manage_roles',
    'require_view_reports',
    'require_communicate',
    'require_manage_attendance',
    'require_manage_admissions',
    
    # Role Shortcuts
    'require_principal',
    'require_teacher',
    'require_admin_staff',
    'require_head_teacher',
    'require_department_head',
    'require_parent',
    
    # Resource Control
    'restrict_to_school',
    
    # HTMX Decorators
    'htmx_required',
    'htmx_permission_required',
    
    # Composite Decorators
    'staff_only',
    'admin_only',
    
    # Utility Functions
    'check_permission',
    'get_user_role',
    'is_principal',
    'is_teacher',
    'is_admin_staff',
    'is_parent',
] 
