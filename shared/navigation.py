"""
UNIFIED NAVIGATION SYSTEM - FINAL VERSION
Handles: Role-Based Access, School Context, Mobile Visibility, and Resilient URLs.
"""
import logging
from django.urls import reverse, NoReverseMatch
from django.apps import apps

logger = logging.getLogger(__name__)

class NavigationItem:
    def __init__(self, label, url_name=None, url=None, icon='circle', permission=None,
                 system_role_types=None, is_public=False, children=None, 
                 requires_school=False, namespace=None, mobile_only=False, 
                 hide_on_mobile=False):
        self.label = label
        self.url_name = url_name
        self.url = url
        self.icon = icon
        self.permission = permission
        self.system_role_types = system_role_types or []
        self.is_public = is_public
        self.children = children or []
        self.requires_school = requires_school
        self.namespace = namespace
        self.mobile_only = mobile_only
        self.hide_on_mobile = hide_on_mobile
        self.is_active = False

    def get_url(self):
        """Resilient URL resolution with fallbacks."""
        if self.url: return self.url
        if not self.url_name: return '#'

        # Try: namespace:url_name
        full_path = f"{self.namespace}:{self.url_name}" if self.namespace else self.url_name
        try:
            return reverse(full_path)
        except NoReverseMatch:
            # Fallback: Just url_name
            try:
                return reverse(self.url_name)
            except NoReverseMatch:
                return '#'

    def is_visible(self, user, role, profile, school):
        """Unified visibility logic for UI Scan bugs."""
        if self.is_public: return True
        if not user or not user.is_authenticated: return False
        if user.is_superuser: return True
        if self.requires_school and not school: return False
        
        # Role-based filter
        if self.system_role_types and role:
            if role.system_role_type not in self.system_role_types:
                return False

        # Permission-based filter
        if self.permission:
            from .decorators.permissions import PermissionChecker
            return PermissionChecker.has_permission(role, self.permission)

        return True

class NavigationBuilder:
    @staticmethod
    def get_navigation(request):
        user = request.user
        school = getattr(request, 'school', None)
        profile, role = None, None

        if user.is_authenticated and school:
            try:
                Profile = apps.get_model('users', 'Profile')
                profile = Profile.objects.select_related('role').filter(user=user, school=school).first()
                if profile: role = profile.role
            except Exception: pass

        # Build Master List
        all_items = NavigationBuilder._get_master_list(user, role, profile, school)
        
        # Filter for Desktop and Mobile
        desktop_nav = [i for i in all_items if not i.mobile_only]
        mobile_nav = [i for i in all_items if not i.hide_on_mobile]

        # Mark Active State
        NavigationBuilder._mark_active(request.path, all_items)
        
        return desktop_nav, mobile_nav, role, profile, school

    @staticmethod
    def _get_master_list(user, role, profile, school):
        items = []
        from .decorators.permissions import PermissionChecker

        # --- Dashboard (Primary) ---
        if school:
            items.append(NavigationItem('Dashboard', 'dashboard', namespace='users', icon='speedometer2', requires_school=True))

        # --- Academic Management ---
        if role and PermissionChecker.has_permission(role, 'manage_academics'):
            acad_children = [
                NavigationItem('Classes', 'class_list', namespace='academics', icon='journal'),
                NavigationItem('Subjects', 'subject_list', namespace='academics', icon='book'),
            ]
            items.append(NavigationItem('Academics', icon='mortarboard', children=acad_children, requires_school=True))

        # --- Admissions ---
        if role and PermissionChecker.has_permission(role, 'manage_admissions'):
            items.append(NavigationItem('Admissions', 'application_list', namespace='admissions', icon='door-open', requires_school=True))

        # --- Students & Parents ---
        if role and PermissionChecker.has_permission(role, 'manage_students'):
            stud_children = [
                NavigationItem('Students', 'student_list', namespace='students', icon='people'),
                NavigationItem('Parents', 'parent_list', namespace='students', icon='person-vcard'),
            ]
            items.append(NavigationItem('Students', icon='person-workspace', children=stud_children, requires_school=True))

        # --- Attendance & Billing ---
        if school:
            items.append(NavigationItem('Attendance', 'dashboard', namespace='attendance', icon='calendar-check', permission='manage_attendance'))
            items.append(NavigationItem('Billing', 'dashboard', namespace='billing', icon='cash-stack', permission='manage_finances'))

        # --- Admin Tools ---
        if role and (PermissionChecker.has_permission(role, 'manage_staff') or PermissionChecker.has_permission(role, 'manage_roles')):
            admin_children = []
            if PermissionChecker.has_permission(role, 'manage_staff'):
                admin_children.append(NavigationItem('Staff', 'staff_list', namespace='users', icon='person-badge'))
            if PermissionChecker.has_permission(role, 'manage_roles'):
                admin_children.append(NavigationItem('Roles', 'role_list', namespace='users', icon='shield-lock'))
            items.append(NavigationItem('Admin', icon='gear-wide-connected', children=admin_children, requires_school=True))

        return items

    @staticmethod
    def _mark_active(path, items):
        for item in items:
            url = item.get_url()
            if url != '#' and path.startswith(url.rstrip('/')):
                item.is_active = True
            if item.children:
                NavigationBuilder._mark_active(path, item.children)
