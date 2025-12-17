"""
UNIFIED NAVIGATION SYSTEM - Single source of truth for all navigation
"""

import logging
from django.urls import reverse
from django.apps import apps

logger = logging.getLogger(__name__)


class NavigationItem:
    """Single navigation item class used across the system."""
    
    def __init__(self, label, url_name=None, url=None, icon=None, permission=None, 
                 badge_count=0, badge_color='primary', system_role_types=None, 
                 is_public=False, children=None, requires_school=False):
        self.label = label
        self.url_name = url_name
        self.url = url
        self.icon = icon or 'circle'
        self.permission = permission
        self.badge_count = badge_count
        self.badge_color = badge_color
        self.system_role_types = system_role_types or []
        self.is_public = is_public
        self.children = children or []
        self.requires_school = requires_school
        self.is_active = False
    
    def get_url(self):
        """Get URL safely."""
        try:
            if self.url:
                return self.url
            elif self.url_name:
                return reverse(self.url_name)
        except Exception as e:
            logger.debug(f"Could not resolve URL for {self.label}: {str(e)}")
        
        return '#'
    
    def is_visible(self, user, role, profile, school):
        """
        Single permission checking logic used everywhere.
        """
        # Public items are always visible
        if self.is_public:
            return True
        
        # Not authenticated - only show public items
        if not user or not user.is_authenticated:
            return False
        
        # Superusers see everything
        if user.is_superuser:
            return True
        
        # Items that require school context
        if self.requires_school and not school:
            return False
        
        # Check if user has profile for this school
        if school and not profile:
            return False
        
        # Check system role types
        if self.system_role_types and role:
            if role.system_role_type in self.system_role_types:
                return True
        
        # Check permission using unified permission checker
        if self.permission:
            return PermissionChecker.has_permission(role, self.permission)
        
        # Default to visible if no restrictions
        return True


class PermissionChecker:
    """
    SINGLE SOURCE OF TRUTH for permission checking.
    """
    
    @staticmethod
    def has_permission(role, permission):
        """Check if role has permission - unified logic."""
        if not role:
            return False
        
        # Super role types get all permissions
        if role.system_role_type in ['principal', 'admin']:
            return True
        
        # Check wildcard permission
        if hasattr(role, 'permissions') and '*' in role.permissions:
            return True
        
        # Check explicit permission in permissions list
        if hasattr(role, 'permissions') and permission in role.permissions:
            return True
        
        # Map permission to role boolean fields
        permission_map = {
            'manage_academics': getattr(role, 'can_manage_academics', False),
            'manage_students': getattr(role, 'can_manage_students', False),
            'manage_staff': getattr(role, 'can_manage_staff', False),
            'manage_roles': getattr(role, 'can_manage_roles', False),
            'manage_finances': getattr(role, 'can_manage_finances', False),
            'view_reports': getattr(role, 'can_view_reports', False),
            'communicate': getattr(role, 'can_communicate', False),
            'manage_admissions': getattr(role, 'can_manage_students', False) or getattr(role, 'system_role_type', '') in ['principal', 'admin'],
            'view_students': (
                getattr(role, 'can_manage_students', False) or 
                getattr(role, 'system_role_type', '') in ['teacher', 'parent']
            ),
            'manage_attendance': (
                getattr(role, 'can_manage_academics', False) or 
                getattr(role, 'system_role_type', '') == 'teacher'
            ),
        }
        
        return permission_map.get(permission, False)


class NavigationBuilder:
    """
    SINGLE navigation builder used across the system.
    """
    
    @staticmethod
    def get_navigation(request):
        """
        Get complete navigation for a request.
        Returns: (desktop_nav, mobile_nav, user_role, profile, school)
        """
        user = request.user
        school = getattr(request, 'school', None)
        profile = None
        role = None
        
        # Get user's profile and role for the current school
        if user.is_authenticated and school:
            try:
                Profile = apps.get_model('users', 'Profile')
                profile = Profile.objects.get(user=user, school=school)
                role = profile.role
            except Exception as e:
                logger.debug(f"No profile found: {e}")
        
        # Build navigation
        if not user.is_authenticated:
            desktop_nav = NavigationBuilder.get_public_navigation()
            mobile_nav = NavigationBuilder.get_mobile_navigation(user, role, profile, school)
        else:
            desktop_nav = NavigationBuilder.get_authenticated_navigation(user, role, profile, school)
            mobile_nav = NavigationBuilder.get_mobile_navigation(user, role, profile, school)
        
        # Mark active items
        NavigationBuilder._mark_active_items(request.path, desktop_nav + mobile_nav)
        
        return desktop_nav, mobile_nav, role, profile, school
    
    @staticmethod
    def get_public_navigation():
        """Navigation for non-logged in users."""
        return [
            NavigationItem('Home', url='/', icon='house', is_public=True),
            NavigationItem('Discover Schools', url_name='school_discovery', icon='search', is_public=True),
            NavigationItem('Apply Now', url_name='admissions:apply_public', icon='pencil-square', is_public=True),
            NavigationItem('Login', url_name='account_login', icon='box-arrow-in-right', is_public=True),
            NavigationItem('Register', url_name='account_signup', icon='person-plus', is_public=True),
        ]
    
    @staticmethod
    def get_authenticated_navigation(user, role, profile, school):
        """Navigation for authenticated users."""
        items = []
        
        # Dashboard - always visible for authenticated users
        items.append(NavigationItem('Dashboard', url_name='users:dashboard', icon='speedometer2', requires_school=True))
        
        # School Selection
        items.append(NavigationItem('My Schools', url_name='users:school_list', icon='building'))
        
        # ADMINISTRATION
        if PermissionChecker.has_permission(role, 'manage_staff'):
            items.append(NavigationItem('Staff', url_name='users:staff_list', icon='person-badge', permission='manage_staff'))
        
        if PermissionChecker.has_permission(role, 'manage_roles'):
            items.append(NavigationItem('Roles', url_name='users:role_list', icon='shield-check', permission='manage_roles'))
        
        # STUDENT MANAGEMENT
        if PermissionChecker.has_permission(role, 'view_students'):
            items.append(NavigationItem('Students', url_name='students:student_list', icon='people', permission='view_students'))
            items.append(NavigationItem('Parents', url_name='students:parent_list', icon='people-fill', permission='view_students'))
        
        # PARENT SECTION
        if role and role.system_role_type == 'parent':
            items.append(NavigationItem('My Children', url_name='students:parent_children', icon='people', system_role_types=['parent']))
            items.append(NavigationItem('Invoices', url_name='billing:parent_invoices', icon='receipt', system_role_types=['parent']))
        
        # ACADEMIC MANAGEMENT
        if PermissionChecker.has_permission(role, 'manage_academics'):
            items.append(NavigationItem('Classes', url_name='core:class_list', icon='journal', permission='manage_academics'))
            items.append(NavigationItem('Subjects', url_name='core:subject_list', icon='book', permission='manage_academics'))
        
        # ADMISSIONS
        if PermissionChecker.has_permission(role, 'manage_admissions'):
            items.append(NavigationItem('Admissions', url_name='admissions:dashboard', icon='door-open', permission='manage_admissions'))
        
        # ATTENDANCE
        if PermissionChecker.has_permission(role, 'manage_attendance'):
            items.append(NavigationItem('Attendance', url_name='attendance:dashboard', icon='check-circle', permission='manage_attendance'))
        
        # BILLING
        if PermissionChecker.has_permission(role, 'manage_finances'):
            items.append(NavigationItem('Billing', url_name='billing:dashboard', icon='currency-dollar', permission='manage_finances'))
        
        # TEACHER APPLICATIONS
        if role and role.system_role_type == 'teacher':
            items.append(NavigationItem('My Applications', url_name='users:my_applications', icon='file-earmark-person', system_role_types=['teacher']))
        
        # SYSTEM SECTION
        items.append(NavigationItem('Profile', url_name='users:profile', icon='person'))
        items.append(NavigationItem('Settings', url_name='users:profile', icon='gear'))
        items.append(NavigationItem('Logout', url_name='account_logout', icon='box-arrow-right'))
        
        return items
    
    @staticmethod
    def get_mobile_navigation(user, role, profile, school):
        """Simplified mobile navigation."""
        items = []
        
        if user.is_authenticated:
            items.append(NavigationItem('Home', url_name='users:dashboard', icon='house', requires_school=True))
            items.append(NavigationItem('Schools', url_name='users:school_list', icon='building'))
            
            if PermissionChecker.has_permission(role, 'manage_admissions'):
                items.append(NavigationItem('Admissions', url_name='admissions:dashboard', icon='door-open', permission='manage_admissions'))
            
            if PermissionChecker.has_permission(role, 'manage_attendance'):
                items.append(NavigationItem('Attendance', url_name='attendance:dashboard', icon='check-circle', permission='manage_attendance'))
            
            if role and role.system_role_type == 'teacher':
                items.append(NavigationItem('My Apps', url_name='users:my_applications', icon='file-earmark-person'))
        else:
            items.append(NavigationItem('Home', url='/', icon='house', is_public=True))
            items.append(NavigationItem('Discover', url_name='school_discovery', icon='search', is_public=True))
            items.append(NavigationItem('Apply', url_name='admissions:apply_public', icon='pencil-square', is_public=True))
        
        items.append(NavigationItem('More', icon='three-dots'))
        
        return items
    
    @staticmethod
    def _mark_active_items(current_path, navigation_items):
        """Mark active navigation items based on current path."""
        for item in navigation_items:
            try:
                item_url = item.get_url()
                if item_url != '#' and current_path.startswith(item_url.rstrip('/')):
                    item.is_active = True
                    break  # Only one active item at a time
            except Exception:
                continue