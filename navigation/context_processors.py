# navigation/context_processors.py
from django.conf import settings

def navigation_menu(request):
    """Enhanced navigation menu that integrates with your Role-based permission system."""
    
    def get_user_role(user, school):
        """Get user role based on your Role model and school context."""
        if not user.is_authenticated:
            return None
        
        if user.is_superuser:
            return {
                'name': 'Super Admin',
                'category': 'administration',
                'permissions': ['*'],  # All permissions
                'is_system_role': True,
                'can_manage_roles': True,
                'can_manage_staff': True,
                'can_manage_students': True,
                'can_manage_academics': True,
                'can_manage_finances': True,
                'can_view_reports': True,
                'can_communicate': True,
            }
        
        # Get user's role for the current school
        try:
            if hasattr(user, 'profile_set') and school:
                profile = user.profile_set.get(school=school)
                return {
                    'name': profile.role.name,
                    'category': profile.role.category,
                    'permissions': profile.role.permissions,
                    'is_system_role': profile.role.is_system_role,
                    'can_manage_roles': profile.role.can_manage_roles,
                    'can_manage_staff': profile.role.can_manage_staff,
                    'can_manage_students': profile.role.can_manage_students,
                    'can_manage_academics': profile.role.can_manage_academics,
                    'can_manage_finances': profile.role.can_manage_finances,
                    'can_view_reports': profile.role.can_view_reports,
                    'can_communicate': profile.role.can_communicate,
                }
        except Exception:
            pass
        
        return None
    
    def has_permission(role, permission):
        """Check if role has specific permission."""
        if not role:
            return False
        
        # Super admin has all permissions
        if role.get('is_system_role') and role.get('name') == 'Super Admin':
            return True
            
        if role.get('permissions') and ('*' in role['permissions'] or permission in role['permissions']):
            return True
        
        # Check boolean permissions from your Role model
        permission_map = {
            'manage_roles': 'can_manage_roles',
            'manage_staff': 'can_manage_staff',
            'manage_students': 'can_manage_students',
            'manage_academics': 'can_manage_academics',
            'manage_finances': 'can_manage_finances',
            'view_reports': 'can_view_reports',
            'communicate': 'can_communicate',
        }
        
        if permission in permission_map:
            return role.get(permission_map[permission], False)
        
        return False
    
    def get_navigation_items(role, school=None):
        """Define comprehensive navigation structure using permission checks."""
        
        # Base navigation structure
        all_items = [
            # Dashboard
            {'type': 'header', 'label': 'Dashboard', 'permission': None},
            {'type': 'item', 'label': 'Overview', 'icon': 'speedometer2', 'url': 'users:dashboard', 'permission': None},
            {'type': 'item', 'label': 'School Stats', 'icon': 'graph-up', 'url': 'core:school_overview_stats', 'permission': 'view_reports'},
            
            # Student Management
            {'type': 'divider', 'permission': 'manage_students'},
            {'type': 'header', 'label': 'Student Management', 'permission': 'manage_students'},
            {'type': 'item', 'label': 'All Students', 'icon': 'people', 'url': 'students:student_list', 'permission': 'manage_students'},
            {'type': 'item', 'label': 'Add Student', 'icon': 'person-plus', 'url': 'students:student_create', 'permission': 'manage_students'},
            {'type': 'item', 'label': 'Parents', 'icon': 'people-fill', 'url': 'students:parent_list', 'permission': 'manage_students'},
            {'type': 'item', 'label': 'Class Groups', 'icon': 'collection', 'url': 'students:class_group_list', 'permission': 'manage_students'},
            
            # Academic Management
            {'type': 'divider', 'permission': 'manage_academics'},
            {'type': 'header', 'label': 'Academic', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Admissions', 'icon': 'door-open', 'url': 'admissions:dashboard', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Classes', 'icon': 'journal', 'url': 'core:class_list', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Subjects', 'icon': 'book', 'url': 'core:subject_list', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Class Categories', 'icon': 'folder', 'url': 'core:class_category_list', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Education Levels', 'icon': 'mortarboard', 'url': 'students:education_level_list', 'permission': 'manage_academics'},
            
            # Attendance
            {'type': 'divider', 'permission': 'manage_academics'},
            {'type': 'header', 'label': 'Attendance', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Dashboard', 'icon': 'check-circle', 'url': 'attendance:dashboard', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Student Attendance', 'icon': 'person-check', 'url': 'attendance:student_attendance_list', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Class Attendance', 'icon': 'collection', 'url': 'attendance:class_group_attendance', 'permission': 'manage_academics'},
            {'type': 'item', 'label': 'Teacher Attendance', 'icon': 'person-badge', 'url': 'attendance:teacher_attendance_list', 'permission': 'manage_staff'},
            {'type': 'item', 'label': 'Reports', 'icon': 'clipboard-data', 'url': 'attendance:reports', 'permission': 'view_reports'},
            
            # Staff & Role Management
            {'type': 'divider', 'permission': 'manage_staff'},
            {'type': 'header', 'label': 'Staff Management', 'permission': 'manage_staff'},
            {'type': 'item', 'label': 'Staff List', 'icon': 'person-badge', 'url': 'users:staff_list', 'permission': 'manage_staff'},
            {'type': 'item', 'label': 'Add Staff', 'icon': 'person-add', 'url': 'users:staff_create', 'permission': 'manage_staff'},
            {'type': 'item', 'label': 'Invite Staff', 'icon': 'envelope', 'url': 'users:staff_invite', 'permission': 'manage_staff'},
            {'type': 'item', 'label': 'Role Management', 'icon': 'shield-check', 'url': 'users:role_list', 'permission': 'manage_roles'},
            
            # Finance Management
            {'type': 'divider', 'permission': 'manage_finances'},
            {'type': 'header', 'label': 'Finance', 'permission': 'manage_finances'},
            {'type': 'item', 'label': 'Billing Dashboard', 'icon': 'currency-dollar', 'url': 'billing:dashboard', 'permission': 'manage_finances'},
            {'type': 'item', 'label': 'Fee Structures', 'icon': 'file-earmark-text', 'url': 'billing:fee_structure_list', 'permission': 'manage_finances'},
            {'type': 'item', 'label': 'Invoices', 'icon': 'receipt', 'url': 'billing:invoice_list', 'permission': 'manage_finances'},
            {'type': 'item', 'label': 'Parent Invoices', 'icon': 'wallet', 'url': 'billing:parent_invoices', 'permission': 'manage_finances'},
            
            # Parent Section
            {'type': 'divider', 'permission': 'communicate'},
            {'type': 'header', 'label': 'Parent Portal', 'permission': 'communicate'},
            {'type': 'item', 'label': 'Parent Dashboard', 'icon': 'house', 'url': 'students:parent_dashboard', 'permission': 'communicate'},
            {'type': 'item', 'label': 'My Children', 'icon': 'people', 'url': 'students:parent_children', 'permission': 'communicate'},
            
            # System
            {'type': 'divider', 'permission': None},
            {'type': 'header', 'label': 'System', 'permission': None},
            {'type': 'item', 'label': 'My Schools', 'icon': 'building', 'url': 'users:school_list', 'permission': None},
            {'type': 'item', 'label': 'Profile', 'icon': 'person', 'url': 'users:profile', 'permission': None},
            {'type': 'item', 'label': 'Settings', 'icon': 'gear', 'url': 'users:profile', 'permission': None},
        ]
        
        # Filter items based on permissions
        filtered_items = []
        for item in all_items:
            if item['type'] in ['divider', 'header']:
                # Include dividers and headers if any following items have permission
                filtered_items.append(item)
            else:
                if has_permission(role, item.get('permission')):
                    filtered_items.append(item)
        
        return filtered_items
    
    def detect_current_section(path):
        """Detect current section from URL path."""
        path_parts = path.strip('/').split('/')
        if path_parts:
            return path_parts[0] if path_parts else 'dashboard'
        return 'dashboard'
    
    # Initialize variables with default values
    navigation_items = []
    current_section = 'home'
    user_role_name = 'Anonymous'
    user_permissions = []
    
    # Get school context
    school = getattr(request, 'school', None)
    
    if request.user.is_authenticated:
        role = get_user_role(request.user, school)
        if role:
            navigation_items = get_navigation_items(role, school)
            user_role_name = role.get('name', 'User')
            user_permissions = role.get('permissions', [])
        else:
            # User is authenticated but has no role for this school
            navigation_items = [
                {'type': 'header', 'label': 'Access'},
                {'type': 'item', 'label': 'Select School', 'icon': 'building', 'url': 'users:school_list', 'permission': None},
                {'type': 'item', 'label': 'Profile', 'icon': 'person', 'url': 'users:profile', 'permission': None},
            ]
            user_role_name = 'User'
            user_permissions = []
        
        current_section = detect_current_section(request.path)
    
    return {
        'navigation_items': navigation_items,
        'current_section': current_section,
        'user_role': user_role_name,
        'user_permissions': user_permissions
    }