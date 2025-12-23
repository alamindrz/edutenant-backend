# shared/navigation.py - FIXED
"""
UNIFIED NAVIGATION SYSTEM - Single source of truth for all navigation
NO circular imports, PROPER URL resolution, CONSISTENT permission checking
"""

import logging
from django.urls import reverse, NoReverseMatch
from django.apps import apps

logger = logging.getLogger(__name__)


class NavigationItem:
    """Single navigation item class used across the system."""

    def __init__(self, label, url_name=None, url=None, icon=None, permission=None,
                 badge_count=0, badge_color='primary', system_role_types=None,
                 is_public=False, children=None, requires_school=False,
                 namespace=None, app_name=None, exact_match=False):
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
        self.namespace = namespace
        self.app_name = app_name
        self.exact_match = exact_match  # For marking active items
        self.is_active = False

    def get_url(self):
        """Get URL safely with namespace support."""
        try:
            if self.url:
                return self.url

            if self.url_name:
                # Build full view name
                parts = []
                if self.namespace:
                    parts.append(self.namespace)
                if self.app_name:
                    parts.append(self.app_name)
                parts.append(self.url_name)

                full_name = ':'.join(parts)
                return reverse(full_name)

        except NoReverseMatch as e:
            logger.debug(f"URL not found for {self.url_name}: {str(e)}")
        except Exception as e:
            logger.debug(f"Error getting URL for {self.label}: {str(e)}")

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
            from .decorators.permissions import PermissionChecker
            return PermissionChecker.has_permission(role, self.permission)

        # Default to visible if no restrictions
        return True


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
        user = request.user if hasattr(request, 'user') else None
        school = getattr(request, 'school', None)
        profile = None
        role = None

        # Get user's profile and role for the current school
        if user and user.is_authenticated and school:
            try:
                Profile = apps.get_model('users', 'Profile')
                profile = Profile.objects.select_related('role').filter(
                    user=user,
                    school=school
                ).first()

                if profile:
                    role = profile.role

            except Exception as e:
                logger.debug(f"No profile found: {e}")

        # Build navigation based on authentication
        if not user or not user.is_authenticated:
            desktop_nav = NavigationBuilder.get_public_navigation()
            mobile_nav = NavigationBuilder.get_mobile_public_navigation()
        else:
            desktop_nav = NavigationBuilder.get_authenticated_navigation(user, role, profile, school)
            mobile_nav = NavigationBuilder.get_mobile_authenticated_navigation(user, role, profile, school)

        # Mark active items
        NavigationBuilder._mark_active_items(request.path, desktop_nav + mobile_nav)

        return desktop_nav, mobile_nav, role, profile, school

    @staticmethod
    def get_public_navigation():
        """Navigation for non-logged in users."""
        return [
            NavigationItem(
                'Home',
                url='/',
                icon='house',
                is_public=True
            ),
            NavigationItem(
                'Discover Schools',
                url_name='school_discovery',
                icon='search',
                is_public=True
            ),
            NavigationItem(
                'Login',
                url_name='account_login',
                icon='box-arrow-in-right',
                is_public=True
            ),
            NavigationItem(
                'Register',
                url_name='account_signup',
                icon='person-plus',
                is_public=True
            ),
        ]

    @staticmethod
    def get_authenticated_navigation(user, role, profile, school):
        """Navigation for authenticated users - COMPLETE version."""
        items = []

        # ============ DASHBOARD ============
        if school:
            items.append(NavigationItem(
                'Dashboard',
                url_name='dashboard',
                namespace='users',
                app_name='dashboard',
                icon='speedometer2',
                requires_school=True
            ))

        # ============ SCHOOL MANAGEMENT ============
        items.append(NavigationItem(
            'My Schools',
            url_name='school_list',
            namespace='users',
            app_name='dashboard',
            icon='building'
        ))

        # ============ ADMINISTRATION SECTION ============
        admin_children = []
        from .decorators.permissions import PermissionChecker

        if role and PermissionChecker.has_permission(role, 'manage_staff'):
            admin_children.append(NavigationItem(
                'Staff',
                url_name='staff_list',
                namespace='users',
                app_name='dashboard',
                icon='person-badge',
                permission='manage_staff'
            ))

        if role and PermissionChecker.has_permission(role, 'manage_roles'):
            admin_children.append(NavigationItem(
                'Roles',
                url_name='role_list',
                namespace='users',
                app_name='dashboard',
                icon='shield-check',
                permission='manage_roles'
            ))

        if admin_children:
            items.append(NavigationItem(
                'Administration',
                icon='gear',
                children=admin_children,
                requires_school=True
            ))

        # ============ STUDENT MANAGEMENT ============
        student_children = []

        if role and PermissionChecker.has_permission(role, 'manage_students'):
            student_children.append(NavigationItem(
                'Students',
                url_name='student_list',
                namespace='students',
                icon='people',
                permission='manage_students'
            ))

            student_children.append(NavigationItem(
                'Parents',
                url_name='parent_list',
                namespace='students',
                icon='people-fill',
                permission='manage_students'
            ))

        if role and role.system_role_type == 'parent':
            student_children.append(NavigationItem(
                'My Children',
                url_name='parent_children',
                namespace='students',
                icon='people',
                system_role_types=['parent']
            ))

        if student_children:
            items.append(NavigationItem(
                'Student Management',
                icon='people',
                children=student_children,
                requires_school=True
            ))

        # ============ ACADEMIC MANAGEMENT ============
        academic_children = []

        if role and PermissionChecker.has_permission(role, 'manage_academics'):
            academic_children.append(NavigationItem(
                'Classes',
                url_name='class_list',
                namespace='academics',
                app_name='core',
                icon='journal',
                permission='manage_academics'
            ))

            academic_children.append(NavigationItem(
                'Subjects',
                url_name='subject_list',
                namespace='academics',
                app_name='core',
                icon='book',
                permission='manage_academics'
            ))

        if academic_children:
            items.append(NavigationItem(
                'Academic Management',
                icon='book',
                children=academic_children,
                requires_school=True
            ))

        # ============ ADMISSIONS ============
        if role and PermissionChecker.has_permission(role, 'manage_admissions'):
            items.append(NavigationItem(
                'Admissions',
                url_name='application_list',
                namespace='admissions',
                icon='door-open',
                permission='manage_admissions',
                requires_school=True
            ))

        # ============ ATTENDANCE ============
        if role and PermissionChecker.has_permission(role, 'manage_attendance'):
            items.append(NavigationItem(
                'Attendance',
                url_name='dashboard',
                namespace='attendance',
                icon='check-circle',
                permission='manage_attendance',
                requires_school=True
            ))

        # ============ BILLING ============
        if role and PermissionChecker.has_permission(role, 'manage_finances'):
            items.append(NavigationItem(
                'Billing',
                url_name='dashboard',
                namespace='billing',
                icon='currency-dollar',
                permission='manage_finances',
                requires_school=True
            ))

        # ============ TEACHER PORTAL ============
        if role and role.system_role_type == 'teacher':
            items.append(NavigationItem(
                'My Applications',
                url_name='my_applications',
                namespace='users',
                app_name='dashboard',
                icon='file-earmark-person',
                system_role_types=['teacher'],
                requires_school=True
            ))

        # ============ USER PROFILE ============
        user_children = []

        user_children.append(NavigationItem(
            'Profile',
            url_name='profile',
            namespace='users',
            app_name='dashboard',
            icon='person'
        ))

        user_children.append(NavigationItem(
            'Settings',
            url_name='profile',
            namespace='users',
            app_name='dashboard',
            icon='gear'
        ))

        # Apply to other schools (if not already in one)
        if not school:
            user_children.append(NavigationItem(
                'Apply to School',
                url_name='apply_public',
                namespace='admissions',
                icon='pencil-square'
            ))

        user_children.append(NavigationItem(
            'Logout',
            url_name='account_logout',
            icon='box-arrow-right'
        ))

        items.append(NavigationItem(
            'Account',
            icon='person-circle',
            children=user_children
        ))

        return items

    @staticmethod
    def get_mobile_public_navigation():
        """Simplified mobile navigation for public users."""
        return [
            NavigationItem('Home', url='/', icon='house', is_public=True),
            NavigationItem('Discover', url_name='school_discovery', icon='search', is_public=True),
            NavigationItem('Login', url_name='account_login', icon='box-arrow-in-right', is_public=True),
        ]

    @staticmethod
    def get_mobile_authenticated_navigation(user, role, profile, school):
        """Simplified mobile navigation for authenticated users."""
        items = []

        # Always show home if we have school context
        if school:
            items.append(NavigationItem(
                'Home',
                url_name='dashboard',
                namespace='users',
                app_name='dashboard',
                icon='house',
                requires_school=True
            ))

        # Schools list
        items.append(NavigationItem(
            'Schools',
            url_name='school_list',
            namespace='users',
            app_name='dashboard',
            icon='building'
        ))

        # Quick access to important sections
        from .decorators.permissions import PermissionChecker

        if role and PermissionChecker.has_permission(role, 'manage_admissions'):
            items.append(NavigationItem(
                'Admissions',
                url_name='dashboard',
                namespace='admissions',
                icon='door-open',
                permission='manage_admissions',
                requires_school=True
            ))

        if role and PermissionChecker.has_permission(role, 'manage_attendance'):
            items.append(NavigationItem(
                'Attendance',
                url_name='dashboard',
                namespace='attendance',
                icon='check-circle',
                permission='manage_attendance',
                requires_school=True
            ))

        if role and role.system_role_type == 'teacher':
            items.append(NavigationItem(
                'My Apps',
                url_name='my_applications',
                namespace='users',
                app_name='dashboard',
                icon='file-earmark-person',
                system_role_types=['teacher'],
                requires_school=True
            ))

        # More menu
        items.append(NavigationItem(
            'More',
            icon='three-dots'
        ))

        return items

    @staticmethod
    def _mark_active_items(current_path, navigation_items):
        """Mark active navigation items based on current path."""
        def mark_item_and_children(item, path):
            item_url = item.get_url()

            if item_url != '#':
                # Check for exact match or prefix match
                if item.exact_match and item_url == path:
                    item.is_active = True
                    return True
                elif not item.exact_match and path.startswith(item_url.rstrip('/')):
                    item.is_active = True
                    return True

            # Check children
            for child in item.children:
                if mark_item_and_children(child, path):
                    item.is_active = True
                    return True

            return False

        for item in navigation_items:
            mark_item_and_children(item, current_path)
