"""
UNIFIED CONTEXT PROCESSOR - Updated for current system
"""

import logging
from django.conf import settings
from .navigation import NavigationBuilder, PermissionChecker  # Updated import
from django.apps import apps

logger = logging.getLogger(__name__)


def unified_context(request):
    """
    SINGLE context processor that provides everything.
    Updated for current project structure.
    """
    context = {}
    
    try:
        # 1. BASIC USER CONTEXT
        user = getattr(request, 'user', None)
        context['user'] = user
        
        # 2. NAVIGATION (using your NavigationBuilder)
        if hasattr(request, 'school'):
            school = request.school
        else:
            school = None
            
        # Get navigation from NavigationBuilder
        desktop_nav, mobile_nav, user_role, user_profile, school_from_nav = NavigationBuilder.get_navigation(request)
        
        # Use school from navigation if request.school is not set
        if school is None and school_from_nav:
            school = school_from_nav
            request.school = school  # Set it on request for consistency
        
        context.update({
            'desktop_navigation': desktop_nav,
            'mobile_navigation': mobile_nav,  # Changed from mobile_bottom_navigation
            'user_role': user_role,  # Keep the full role object
            'user_profile': user_profile,
            'current_school': school,
            'has_school_context': bool(school),  # Add this for easy checks
        })
        
        # 3. SCHOOL CONTEXT
        if school:
            context.update({
                'school_primary_color': getattr(school, 'primary_color', '#007bff'),
                'school_secondary_color': getattr(school, 'secondary_color', '#6c757d'),
                'school_logo': school.logo.url if hasattr(school, 'logo') and school.logo else None,
                'school_name': school.name,
            })
        
        # 4. BILLING CONTEXT - Updated for safety
        try:
            if school and user and user.is_authenticated:
                # Check if billing app is installed
                try:
                    Invoice = apps.get_model('billing', 'Invoice')
                    
                    # Check for parent invoices if user is a parent
                    parent = getattr(user, 'parent', None)
                    if parent:
                        context['pending_invoices_count'] = Invoice.objects.filter(
                            parent=parent,
                            status__in=['pending', 'overdue']
                        ).count()
                        context['overdue_invoices_count'] = Invoice.objects.filter(
                            parent=parent,
                            status='overdue'
                        ).count()
                    
                    # Check for school invoices
                    if school:
                        context['school_pending_invoices'] = Invoice.objects.filter(
                            school=school,
                            status__in=['pending', 'overdue']
                        ).count()
                        
                except LookupError:
                    logger.debug("Billing app not installed")
                    pass
        except Exception as e:
            logger.debug(f"Billing context error: {e}")
        
        # 5. ADMISSIONS CONTEXT - For pending applications
        try:
            if school and user_role:
                Application = apps.get_model('admissions', 'Application')
                
                # Count pending applications (for admins)
                if PermissionChecker.has_permission(user_role, 'manage_admissions'):
                    context['pending_applications_count'] = Application.objects.filter(
                        school=school,
                        status='pending'
                    ).count()
                
                # Count user's applications (for teachers/staff)
                if user.is_authenticated:
                    context['my_pending_applications'] = Application.objects.filter(
                        applicant=user,
                        school=school,
                        status='pending'
                    ).count()
                    
        except LookupError:
            logger.debug("Admissions app not installed")
        except Exception as e:
            logger.debug(f"Admissions context error: {e}")
        
        # 6. PERMISSION FLAGS (for templates) - Using PermissionChecker
        if user_role:
            context.update({
                'user_can_manage_admissions': PermissionChecker.has_permission(user_role, 'manage_admissions'),
                'user_can_manage_staff': PermissionChecker.has_permission(user_role, 'manage_staff'),
                'user_can_manage_attendance': PermissionChecker.has_permission(user_role, 'manage_attendance'),
                'user_can_view_students': PermissionChecker.has_permission(user_role, 'view_students'),
                'user_can_manage_academics': PermissionChecker.has_permission(user_role, 'manage_academics'),
                'user_can_manage_finances': PermissionChecker.has_permission(user_role, 'manage_finances'),
                'user_can_manage_roles': PermissionChecker.has_permission(user_role, 'manage_roles'),
                'user_can_communicate': PermissionChecker.has_permission(user_role, 'communicate'),
                'user_can_view_reports': PermissionChecker.has_permission(user_role, 'view_reports'),
            })
        
        # 7. THEME - Check multiple sources
        theme = (
            request.session.get('theme') or
            request.COOKIES.get('theme') or
            getattr(settings, 'DEFAULT_THEME', 'light')
        )
        context['current_theme'] = theme
        
        # 8. NOTIFICATIONS (from middleware)
        if hasattr(request, 'unread_notifications'):
            context['unread_notifications'] = request.unread_notifications
            context['notification_count'] = request.notification_count
        
        # 9. TIMEZONE (from middleware)
        if hasattr(request, 'timezone'):
            context['current_timezone'] = request.timezone
        
        # 10. SETTINGS & CONFIG
        context.update({
            'DEBUG': settings.DEBUG,
            'PAYSTACK_PUBLIC_KEY': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
            'SITE_NAME': getattr(settings, 'SITE_NAME', 'Edutenant'),
            'BRAND_NAME': 'Edutenant',  # Hardcoded for consistency
        })
        
        # 11. STATS FOR DASHBOARD
        if school and user_role:
            try:
                Student = apps.get_model('students', 'Student')
                Staff = apps.get_model('users', 'Staff')
                Class = apps.get_model('core', 'Class')
                
                stats = {
                    'student_count': Student.objects.filter(school=school, is_active=True).count(),
                    'staff_count': Staff.objects.filter(school=school, is_active=True).count(),
                    'class_count': Class.objects.filter(school=school, is_active=True).count(),
                }
                
                # Role-specific stats
                if hasattr(user_role, 'system_role_type'):
                    if user_role.system_role_type == 'teacher':
                        # Get teacher's assigned classes
                        try:
                            teacher = Staff.objects.get(user=user, school=school)
                            if hasattr(teacher, 'assigned_classes'):
                                stats['assigned_classes'] = teacher.assigned_classes.count()
                                # Count students in assigned classes
                                student_count = 0
                                for class_obj in teacher.assigned_classes.all():
                                    student_count += class_obj.students.count()
                                stats['assigned_students'] = student_count
                        except Staff.DoesNotExist:
                            pass
                    
                    elif user_role.system_role_type == 'parent':
                        try:
                            Parent = apps.get_model('students', 'Parent')
                            parent = Parent.objects.get(user=user, school=school)
                            stats['children_count'] = parent.children.count()
                        except Parent.DoesNotExist:
                            pass
                
                context['stats'] = stats
                
            except LookupError as e:
                logger.debug(f"Model not found for stats: {e}")
            except Exception as e:
                logger.debug(f"Error calculating stats: {e}")
        
    except Exception as e:
        logger.error(f"Error in unified context processor: {e}", exc_info=True)
        # Provide minimal context on error
        context.update({
            'desktop_navigation': [],
            'mobile_navigation': [],
            'current_school': None,
            'user_role': None,
            'user_profile': None,
            'has_school_context': False,
            'current_theme': 'light',
            'BRAND_NAME': 'Edutenant',
        })
    
    return context