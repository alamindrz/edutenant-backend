# core/decorators_unified.py
"""
Unified decorators for role-based access control and school context.
These decorators work across all apps and handle both permissions and school context.
"""
from functools import wraps
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.apps import apps
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


# ===== HELPER FUNCTIONS =====
def _get_user_profile(user, school):
    """Get user's profile for a specific school."""
    try:
        Profile = apps.get_model('users', 'Profile')
        return Profile.objects.get(user=user, school=school)
    except Profile.DoesNotExist:
        logger.warning(f"No profile found for user {user.id} in school {school.id if school else 'None'}")
        return None
    except Exception as e:
        logger.error(f"Error getting profile for user {user.id}: {e}")
        return None


def _has_permission(user, school, permission):
    """Check if user has specific permission for school."""
    if not user or not school:
        return False
    
    profile = _get_user_profile(user, school)
    if not profile or not profile.role:
        return False
    
    # System admins have all permissions
    if profile.role.system_role_type == 'super_admin':
        return True
    
    # Check specific permission
    permissions = set(profile.role.permissions)
    return '*' in permissions or permission in permissions


def _get_current_school(request):
    """Get current school from request."""
    # Priority 1: School from middleware
    if hasattr(request, 'school') and request.school:
        return request.school
    
    # Priority 2: User's current_school
    if request.user.is_authenticated and hasattr(request.user, 'current_school'):
        return request.user.current_school
    
    # Priority 3: First school from user's profiles
    if request.user.is_authenticated:
        try:
            Profile = apps.get_model('users', 'Profile')
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                return profile.school
        except Exception as e:
            logger.error(f"Error getting school from profiles: {e}")
    
    return None


# ===== MAIN DECORATORS =====
def require_school_context(view_func):
    """
    Decorator to ensure school context is available.
    Redirects to school selection if no school context.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Skip if it's a school onboarding or public page
        public_paths = ['/', '/accounts/', '/schools/onboarding/', '/invitations/']
        if any(request.path.startswith(path) for path in public_paths):
            return view_func(request, *args, **kwargs)
        
        school = _get_current_school(request)
        
        if not school:
            messages.warning(request, "Please select a school to continue.")
            return redirect('users:school_list')
        
        # Add school to request for consistency
        if not hasattr(request, 'school') or not request.school:
            request.school = school
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def require_role(permission, redirect_url=None):
    """
    Decorator to require specific permission.
    
    Args:
        permission: Permission string (e.g., 'manage_staff', 'manage_students')
        redirect_url: URL to redirect if permission denied (default: dashboard)
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        @require_school_context
        def _wrapped_view(request, *args, **kwargs):
            school = _get_current_school(request)
            
            if not school:
                messages.error(request, "No school context available.")
                return redirect('users:school_list')
            
            if not _has_permission(request.user, school, permission):
                logger.warning(
                    f"Permission denied for user {request.user.id} "
                    f"on school {school.id} for permission {permission}"
                )
                messages.error(
                    request, 
                    f"You don't have permission to access this page. "
                    f"Required: {permission.replace('_', ' ').title()}"
                )
                
                # Default redirect to dashboard
                if not redirect_url:
                    return redirect('users:dashboard')
                return redirect(redirect_url)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


def require_specific_role(system_role_type, redirect_url=None):
    """
    Decorator to require specific system role type.
    
    Args:
        system_role_type: System role type (e.g., 'principal', 'teacher')
        redirect_url: URL to redirect if role doesn't match
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        @require_school_context
        def _wrapped_view(request, *args, **kwargs):
            school = _get_current_school(request)
            
            if not school:
                messages.error(request, "No school context available.")
                return redirect('users:school_list')
            
            profile = _get_user_profile(request.user, school)
            if not profile or not profile.role:
                messages.error(request, "No role assigned for this school.")
                return redirect('users:dashboard')
            
            if profile.role.system_role_type != system_role_type:
                logger.warning(
                    f"Role mismatch for user {request.user.id}. "
                    f"Required: {system_role_type}, Has: {profile.role.system_role_type}"
                )
                messages.error(
                    request,
                    f"This page is only accessible to {system_role_type.replace('_', ' ').title()}s."
                )
                
                if not redirect_url:
                    return redirect('users:dashboard')
                return redirect(redirect_url)
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


# ===== PERMISSION-SPECIFIC SHORTCUT DECORATORS =====
def require_manage_staff(view_func):
    """Shortcut decorator for managing staff."""
    return require_role('manage_staff')(view_func)


def require_manage_students(view_func):
    """Shortcut decorator for managing students."""
    return require_role('manage_students')(view_func)


def require_manage_academics(view_func):
    """Shortcut decorator for managing academics."""
    return require_role('manage_academics')(view_func)


def require_manage_finances(view_func):
    """Shortcut decorator for managing finances."""
    return require_role('manage_finances')(view_func)


def require_manage_roles(view_func):
    """Shortcut decorator for managing roles."""
    return require_role('manage_roles')(view_func)


def require_view_reports(view_func):
    """Shortcut decorator for viewing reports."""
    return require_role('view_reports')(view_func)


def require_communicate(view_func):
    """Shortcut decorator for sending communications."""
    return require_role('communicate')(view_func)


def require_manage_attendance(view_func):
    """Shortcut decorator for managing attendance."""
    return require_role('manage_attendance')(view_func)


# ===== ROLE-SPECIFIC SHORTCUT DECORATORS =====
def require_principal(view_func):
    """Shortcut decorator for principals only."""
    return require_specific_role('principal')(view_func)


def require_teacher(view_func):
    """Shortcut decorator for teachers only."""
    return require_specific_role('teacher')(view_func)


def require_admin_staff(view_func):
    """Shortcut decorator for admin staff only."""
    return require_specific_role('admin_staff')(view_func)


def require_head_teacher(view_func):
    """Shortcut decorator for head teachers only."""
    return require_specific_role('head_teacher')(view_func)


def require_department_head(view_func):
    """Shortcut decorator for department heads only."""
    return require_specific_role('department_head')(view_func)


# ===== SCHOOL-SPECIFIC DECORATORS =====
def require_school_owner(view_func):
    """
    Decorator for school owners/creators.
    Only the user who created the school can access.
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        school_id = kwargs.get('school_id') or kwargs.get('pk')
        
        if not school_id:
            messages.error(request, "School ID required.")
            return redirect('users:school_list')
        
        School = apps.get_model('core', 'School')
        school = get_object_or_404(School, id=school_id)
        
        # Check if user is the creator (you'll need to add created_by field to School model)
        # For now, we'll check if user is principal in the school
        profile = _get_user_profile(request.user, school)
        if not profile or profile.role.system_role_type != 'principal':
            messages.error(request, "Only school administrators can access this page.")
            return redirect('users:dashboard')
        
        request.school = school
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def restrict_to_school(view_func):
    """
    Decorator to ensure user only accesses resources from their current school.
    Used for detail views to prevent cross-school access.
    """
    @wraps(view_func)
    @login_required
    @require_school_context
    def _wrapped_view(request, *args, **kwargs):
        school = _get_current_school(request)
        
        if not school:
            messages.error(request, "No school context available.")
            return redirect('users:school_list')
        
        # Get the object and check if it belongs to the school
        # This requires the model to have a 'school' foreign key
        model_name = None
        object_id = None
        
        # Try to find model name and object ID from kwargs
        for key, value in kwargs.items():
            if key.endswith('_id'):
                model_name = key.replace('_id', '')
                object_id = value
                break
            elif key == 'pk':
                # Need to know model from URL pattern - we'll handle this in the view
                pass
        
        if model_name and object_id:
            try:
                # Try to get the model
                model = apps.get_model('core', model_name.title())
                obj = get_object_or_404(model, id=object_id, school=school)
                kwargs[model_name] = obj
            except LookupError:
                # Try other common app names
                for app_label in ['users', 'students', 'admissions', 'billing', 'attendance']:
                    try:
                        model = apps.get_model(app_label, model_name.title())
                        obj = get_object_or_404(model, id=object_id, school=school)
                        kwargs[model_name] = obj
                        break
                    except LookupError:
                        continue
            except Exception as e:
                logger.error(f"Error in restrict_to_school: {e}")
                messages.error(request, "Resource not found or access denied.")
                return redirect('users:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


# ===== COMBINATION DECORATORS =====
def staff_only(view_func):
    """Combination decorator for staff-only areas."""
    @wraps(view_func)
    @login_required
    @require_school_context
    def _wrapped_view(request, *args, **kwargs):
        school = _get_current_school(request)
        profile = _get_user_profile(request.user, school)
        
        if not profile:
            messages.error(request, "You are not assigned to this school.")
            return redirect('users:school_list')
        
        # Check if user has any staff permission
        permissions = set(profile.role.permissions)
        if not permissions and profile.role.system_role_type != 'super_admin':
            messages.error(request, "Staff access required.")
            return redirect('users:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def admin_only(view_func):
    """Combination decorator for admin-only areas (manage_staff or manage_roles)."""
    @wraps(view_func)
    @login_required
    @require_school_context
    def _wrapped_view(request, *args, **kwargs):
        school = _get_current_school(request)
        
        if not _has_permission(request.user, school, 'manage_staff') and \
           not _has_permission(request.user, school, 'manage_roles'):
            messages.error(request, "Administrator access required.")
            return redirect('users:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


# ===== HTMX-SPECIFIC DECORATORS =====
def htmx_required(view_func):
    """
    Decorator to require HTMX request headers.
    Returns 400 for non-HTMX requests.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.headers.get('HX-Request'):
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'HTMX request required'}, 
                status=400
            )
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def htmx_permission_required(permission):
    """
    HTMX-specific permission decorator.
    Returns JSON error for HTMX requests, redirects for normal requests.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            school = _get_current_school(request)
            
            if not _has_permission(request.user, school, permission):
                if request.headers.get('HX-Request'):
                    from django.http import JsonResponse
                    return JsonResponse(
                        {'error': 'Permission denied'}, 
                        status=403
                    )
                else:
                    messages.error(request, "Permission denied.")
                    return redirect('users:dashboard')
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator


# ===== UTILITY FUNCTIONS FOR VIEWS =====
def check_permission(user, school, permission):
    """Utility function to check permissions in views."""
    return _has_permission(user, school, permission)


def get_user_role(user, school):
    """Get user's role for a school."""
    profile = _get_user_profile(user, school)
    return profile.role if profile else None


def is_principal(user, school):
    """Check if user is principal in school."""
    profile = _get_user_profile(user, school)
    return profile and profile.role.system_role_type == 'principal'


def is_teacher(user, school):
    """Check if user is teacher in school."""
    profile = _get_user_profile(user, school)
    return profile and profile.role.system_role_type == 'teacher'


def is_admin_staff(user, school):
    """Check if user is admin staff in school."""
    profile = _get_user_profile(user, school)
    return profile and profile.role.system_role_type == 'admin_staff'


# ===== DECORATOR REGISTRY (for debugging) =====
def _decorator_registry():
    """Returns all available decorators for documentation."""
    return {
        'school_context': require_school_context,
        'role_required': require_role,
        'specific_role': require_specific_role,
        'manage_staff': require_manage_staff,
        'manage_students': require_manage_students,
        'manage_academics': require_manage_academics,
        'manage_finances': require_manage_finances,
        'manage_roles': require_manage_roles,
        'view_reports': require_view_reports,
        'communicate': require_communicate,
        'manage_attendance': require_manage_attendance,
        'principal': require_principal,
        'teacher': require_teacher,
        'admin_staff': require_admin_staff,
        'head_teacher': require_head_teacher,
        'department_head': require_department_head,
        'school_owner': require_school_owner,
        'restrict_school': restrict_to_school,
        'staff_only': staff_only,
        'admin_only': admin_only,
        'htmx_required': htmx_required,
        'htmx_permission': htmx_permission_required,
    } 