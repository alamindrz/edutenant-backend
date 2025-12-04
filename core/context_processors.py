# core/context_processors.py
import logging
from django.conf import settings
from billing.models import SchoolSubscription, Invoice
from users.models import School

logger = logging.getLogger(__name__)


def billing_context(request):
    """
    Context processor for billing-related template variables.
    """
    context = {}

    try:
        # Basic billing configs
        context['billing_settings'] = getattr(settings, 'BILLING_SETTINGS', {})
        context['subscription_plans'] = getattr(settings, 'SUBSCRIPTION_PLANS', {})
        context['paystack_public_key'] = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')

        # ---------------------------
        #  SCHOOL SUBSCRIPTION LOGIC
        # ---------------------------
        if getattr(request, 'school', None):
            subscription = SchoolSubscription.objects.filter(
                school=request.school,
                status='active'
            ).first()

            # If no active subscription, allow trialing as fallback
            if not subscription:
                subscription = SchoolSubscription.objects.filter(
                    school=request.school,
                    status='trialing'
                ).first()

            if subscription:
                context['current_subscription'] = subscription
                context['subscription_plan'] = subscription.plan
                context['is_trial'] = subscription.status == 'trialing'
                context['days_until_expiry'] = subscription.days_remaining

                context['subscription_expiring_soon'] = (
                    subscription.days_remaining <= 7
                )
            else:
                context['current_subscription'] = None
                context['subscription_plan'] = 'basic'
                context['is_trial'] = False

        # ---------------------------
        #  USER BILLING LOGIC
        # ---------------------------
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
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
                else:
                    context['pending_invoices_count'] = 0
                    context['overdue_invoices_count'] = 0

            except Exception as e:
                logger.debug(f"Error getting user billing info: {e}")
                context['pending_invoices_count'] = 0
                context['overdue_invoices_count'] = 0

        # ---------------------------
        #  PLATFORM FEES
        # ---------------------------
        billing_settings = context['billing_settings']
        context['platform_fee_percent'] = billing_settings.get('PLATFORM_FEE_PERCENT', 0.015) * 100
        context['paystack_fee_percent'] = billing_settings.get('PAYSTACK_FEE_PERCENT', 0.015) * 100
        context['paystack_fixed_fee'] = billing_settings.get('PAYSTACK_FIXED_FEE', 15.00)

    except Exception as e:
        logger.error(f"Error in billing context processor: {e}")
        context.update({
            'billing_settings': {},
            'subscription_plans': {},
            'paystack_public_key': '',
            'pending_invoices_count': 0,
            'overdue_invoices_count': 0
        })

    return context



def school_context(request):
    """
    Context processor for school-related template variables.
    """
    context = {}
    
    try:
        # Add school to context if available
        if hasattr(request, 'school') and request.school:
            context['current_school'] = request.school
            
            # Add school settings
            context['school_primary_color'] = request.school.primary_color or '#007bff'
            context['school_secondary_color'] = request.school.secondary_color or '#6c757d'
            context['school_logo'] = request.school.logo.url if request.school.logo else None
            context['school_name'] = request.school.name
            
        # Add current school from user if no school from request
        elif hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'current_school') and request.user.current_school:
                context['current_school'] = request.user.current_school
                context['school_name'] = request.user.current_school.name
        
        # Add multi-tenant info
        context['is_multi_tenant'] = True
        context['current_domain'] = request.get_host()
        
    except Exception as e:
        logger.error(f"Error in school context processor: {e}")
        context['current_school'] = None
        context['school_name'] = 'Edusuite'
        context['is_multi_tenant'] = False
    
    return context

def subscription_context(request):
    """
    Context processor specifically for subscription information.
    """
    context = {}
    
    try:
        # Get subscription plans
        plans = getattr(settings, 'SUBSCRIPTION_PLANS', {})
        context['subscription_plans'] = plans
        
        # Add plan limits for current school
        if hasattr(request, 'school') and request.school:
            current_plan = 'basic'  # Default
            
            # Try to get current plan from subscription
            try:
                subscription = SchoolSubscription.objects.filter(
                    school=request.school,
                    is_active=True
                ).first()
                
                if subscription:
                    current_plan = subscription.plan
                    context['current_plan_limits'] = {
                        'max_students': plans.get(current_plan, {}).get('max_students', 50),
                        'max_staff': plans.get(current_plan, {}).get('max_staff', 5),
                        'price_monthly': plans.get(current_plan, {}).get('price_monthly', 0),
                        'price_yearly': plans.get(current_plan, {}).get('price_yearly', 0),
                    }
                    
                    # Check if school is near limits
                    student_count = getattr(request.school, 'student_count', 0)
                    staff_count = getattr(request.school, 'staff_count', 0)
                    
                    max_students = context['current_plan_limits']['max_students']
                    max_staff = context['current_plan_limits']['max_staff']
                    
                    context['near_student_limit'] = student_count >= (max_students * 0.8)
                    context['near_staff_limit'] = staff_count >= (max_staff * 0.8)
                    context['student_usage_percent'] = (student_count / max_students * 100) if max_students > 0 else 0
                    context['staff_usage_percent'] = (staff_count / max_staff * 100) if max_staff > 0 else 0
                    
            except Exception as e:
                logger.debug(f"Error getting subscription context: {e}")
        
    except Exception as e:
        logger.error(f"Error in subscription context processor: {e}")
    
    return context




def school_context(request):
    """Add school context to all templates."""
    context = {}
    if hasattr(request, 'school') and request.school:
        context.update({
            'current_school': request.school,
            'school_primary_color': request.school.primary_color,
            'school_secondary_color': request.school.secondary_color,
            'school_logo': request.school.logo,
            'hide_platform_branding': request.school.hide_platform_branding,
        })
    return context