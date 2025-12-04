from functools import wraps
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import redirect
from django.contrib import messages

def require_role(permission=None):
    """Decorator to require specific role permissions using boolean fields AND permissions list."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('account_login')
            
            # Check if user has a profile for the current school
            if hasattr(request, 'school') and request.school:
                try:
                    profile = request.user.profile_set.get(school=request.school)
                    role = profile.role
                    
                    if permission:
                        # ✅ FIRST: Check for wildcard permission - grants access to everything
                        if role.permissions and '*' in role.permissions:
                            return view_func(request, *args, **kwargs)
                        
                        # ✅ SECOND: Check if permission is explicitly in permissions list
                        if role.permissions and permission in role.permissions:
                            return view_func(request, *args, **kwargs)
                        
                        # ✅ THIRD: Map permission strings to role boolean fields
                        permission_map = {
                            'manage_academics': role.can_manage_academics,
                            'manage_students': role.can_manage_students,
                            'manage_staff': role.can_manage_staff,
                            'manage_roles': role.can_manage_roles,
                            'manage_finances': role.can_manage_finances,
                            'view_reports': role.can_view_reports,
                            'communicate': role.can_communicate,
                            'manage_admissions': role.can_manage_students,  # Admissions falls under student management
                        }
                        
                        # Check if user has the required permission via boolean field
                        has_permission = permission_map.get(permission, False)
                        
                        if not has_permission and not request.user.is_superuser:
                            messages.error(request, f"You don't have permission to {permission.replace('_', ' ')}.")
                            return redirect('users:dashboard')
                    
                except Exception as e:
                    messages.error(request, "No valid profile found for this school.")
                    return redirect('users:school_list')
            else:
                # No school context - redirect to school selection
                messages.warning(request, "Please select a school first.")
                return redirect('users:school_list')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def require_school_context(view_func):
    """Decorator to require valid school context."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request, 'school') or not request.school:
            # Try to set school from user's current_school
            if request.user.is_authenticated and request.user.current_school:
                request.school = request.user.current_school
            else:
                # Redirect to school selection
                messages.warning(request, "Please select a school to continue.")
                return redirect('users:school_list')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view