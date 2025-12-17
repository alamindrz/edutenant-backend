"""
UNIFIED CONTEXT PROCESSOR - Single source for all template variables
"""

import logging
from django.conf import settings
from .navigation_unified import NavigationBuilder

logger = logging.getLogger(__name__)


def unified_context(request):
    """
    SINGLE context processor that provides everything.
    Replaces all other context processors.
    """
    context = {}
    
    try:
        # 1. NAVIGATION
        desktop_nav, mobile_nav, user_role, user_profile, school = NavigationBuilder.get_navigation(request)
        
        context.update({
            'desktop_navigation': desktop_nav,
            'mobile_bottom_navigation': mobile_nav,
            'user_role': user_role.name if user_role else None,
            'user_profile': user_profile,
            'current_school': school,
        })
        
        # 2. SCHOOL CONTEXT
        if school:
            context.update({
                'school_primary_color': school.primary_color or '#007bff',
                'school_secondary_color': school.secondary_color or '#6c757d',
                'school_logo': school.logo.url if school.logo else None,
                'school_name': school.name,
            })
        
        # 3. BILLING CONTEXT
        try:
            if school:
                from billing.models import SchoolSubscription, Invoice
                
                # School subscription
                subscription = SchoolSubscription.objects.filter(
                    school=school,
                    status='active'
                ).first() or SchoolSubscription.objects.filter(
                    school=school,
                    status='trialing'
                ).first()
                
                if subscription:
                    context['current_subscription'] = subscription
                    context['subscription_plan'] = subscription.plan
                    context['is_trial'] = subscription.status == 'trialing'
                    context['days_until_expiry'] = subscription.days_remaining
                    context['subscription_expiring_soon'] = subscription.days_remaining <= 7
            
            # User billing info
            if request.user.is_authenticated:
                if hasattr(request.user, 'parent'):
                    parent = request.user.parent
                    context['pending_invoices_count'] = Invoice.objects.filter(
                        parent=parent,
                        status__in=['pending', 'overdue']
                    ).count()
                    context['overdue_invoices_count'] = Invoice.objects.filter(
                        parent=parent,
                        status='overdue'
                    ).count()
        except Exception as e:
            logger.debug(f"Billing context error: {e}")
        
        # 4. PERMISSION FLAGS (for templates)
        if user_role:
            context.update({
                'user_can_manage_admissions': NavigationBuilder.PermissionChecker.has_permission(user_role, 'manage_admissions'),
                'user_can_manage_staff': NavigationBuilder.PermissionChecker.has_permission(user_role, 'manage_staff'),
                'user_can_manage_attendance': NavigationBuilder.PermissionChecker.has_permission(user_role, 'manage_attendance'),
                'user_can_view_students': NavigationBuilder.PermissionChecker.has_permission(user_role, 'view_students'),
                'user_can_manage_academics': NavigationBuilder.PermissionChecker.has_permission(user_role, 'manage_academics'),
                'user_can_manage_finances': NavigationBuilder.PermissionChecker.has_permission(user_role, 'manage_finances'),
            })
        
        # 5. THEME
        context['current_theme'] = request.session.get('theme', 'light')
        
        # 6. SETTINGS
        context.update({
            'paystack_public_key': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
            'debug': settings.DEBUG,
        })
        
    except Exception as e:
        logger.error(f"Error in unified context processor: {e}", exc_info=True)
        # Provide minimal context on error
        context.update({
            'desktop_navigation': [],
            'mobile_bottom_navigation': [],
            'current_school': None,
            'user_role': None,
        })
    
    return context