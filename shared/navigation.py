"""
UNIFIED NAVIGATION SYSTEM - Fixed with resilient URL resolution
"""

import logging
from django.urls import reverse, NoReverseMatch
from django.apps import apps

logger = logging.getLogger(__name__)

class NavigationItem:
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
        self.exact_match = exact_match
        self.is_active = False

    def get_url(self):
        """Get URL safely with fallback for nested namespaces."""
        if self.url:
            return self.url

        if not self.url_name:
            return '#'

        # 1. Try building the full name: namespace:app_name:url_name
        parts = []
        if self.namespace:
            parts.append(self.namespace)
        if self.app_name:
            parts.append(self.app_name)
        parts.append(self.url_name)
        
        full_name = ':'.join(parts)

        try:
            return reverse(full_name)
        except NoReverseMatch:
            # 2. FALLBACK: Try namespace:url_name (skip app_name)
            if self.namespace and self.app_name:
                try:
                    fallback_name = f"{self.namespace}:{self.url_name}"
                    return reverse(fallback_name)
                except NoReverseMatch:
                    pass
            
            # 3. SECOND FALLBACK: Try just the url_name (no namespace)
            try:
                return reverse(self.url_name)
            except NoReverseMatch:
                logger.debug(f"URL Resolution failed for: {full_name}")
                return '#'

    def is_visible(self, user, role, profile, school):
        if self.is_public: return True
        if not user or not user.is_authenticated: return False
        if user.is_superuser: return True
        if self.requires_school and not school: return False
        if school and not profile: return False

        if self.system_role_types and role:
            if role.system_role_type in self.system_role_types:
                return True

        if self.permission:
            # Local import to prevent circular dependency
            from .decorators.permissions import PermissionChecker
            return PermissionChecker.has_permission(role, self.permission)

        return True

class NavigationBuilder:
    @staticmethod
    def get_navigation(request):
        user = request.user if hasattr(request, 'user') else None
        school = getattr(request, 'school', None)
        profile = None
        role = None

        if user and user.is_authenticated and school:
            try:
                Profile = apps.get_model('users', 'Profile')
                profile = Profile.objects.select_related('role').filter(
                    user=user, school=school
                ).first()
                if profile:
                    role = profile.role
            except Exception as e:
                logger.debug(f"Profile error: {e}")

        if not user or not user.is_authenticated:
            desktop_nav = NavigationBuilder.get_public_navigation()
            mobile_nav = NavigationBuilder.get_mobile_public_navigation()
        else:
            desktop_nav = NavigationBuilder.get_authenticated_navigation(user, role, profile, school)
            mobile_nav = NavigationBuilder.get_mobile_authenticated_navigation(user, role, profile, school)

        NavigationBuilder._mark_active_items(request.path, desktop_nav + mobile_nav)
        return desktop_nav, mobile_nav, role, profile, school

    @staticmethod
    def get_public_navigation():
        return [
            NavigationItem('Home', url='/', icon='house', is_public=True),
            NavigationItem('Discover Schools', url_name='school_discovery', icon='search', is_public=True),
            NavigationItem('Login', url_name='account_login', icon='box-arrow-in-right', is_public=True),
        ]

    @staticmethod
    def get_authenticated_navigation(user, role, profile, school):
        items = []
        from .decorators.permissions import PermissionChecker

        # Dashboard
        if school:
            items.append(NavigationItem(
                'Dashboard', url_name='dashboard', namespace='users', icon='speedometer2', requires_school=True
            ))

        # Admin Section
        admin_children = []
        if role and PermissionChecker.has_permission(role, 'manage_staff'):
            admin_children.append(NavigationItem('Staff', url_name='staff_list', namespace='users', icon='person-badge'))
        if role and PermissionChecker.has_permission(role, 'manage_roles'):
            admin_children.append(NavigationItem('Roles', url_name='role_list', namespace='users', icon='shield-check'))
        
        if admin_children:
            items.append(NavigationItem('Administration', icon='gear', children=admin_children, requires_school=True))

        # Academics
        if role and PermissionChecker.has_permission(role, 'manage_academics'):
            items.append(NavigationItem(
                'Classes', url_name='class_list', namespace='academics', icon='journal'
            ))

        # Account / Profile
        user_children = [
            NavigationItem('Profile', url_name='profile', namespace='users', icon='person'),
            NavigationItem('Logout', url_name='account_logout', icon='box-arrow-right'),
        ]
        items.append(NavigationItem('Account', icon='person-circle', children=user_children))

        return items

    @staticmethod
    def get_mobile_public_navigation():
        return [NavigationItem('Home', url='/', icon='house', is_public=True)]

    @staticmethod
    def get_mobile_authenticated_navigation(user, role, profile, school):
        # Simplified mobile version
        items = [NavigationItem('Dashboard', url_name='dashboard', namespace='users', icon='house')]
        return items

    @staticmethod
    def _mark_active_items(current_path, navigation_items):
        def mark_item_and_children(item, path):
            item_url = item.get_url()
            if item_url != '#' and path.startswith(item_url.rstrip('/')):
                item.is_active = True
                return True
            for child in item.children:
                if mark_item_and_children(child, path):
                    item.is_active = True
                    return True
            return False

        for item in navigation_items:
            mark_item_and_children(item, current_path)
