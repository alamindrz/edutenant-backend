# students/views_parent.py
"""
CLEANED PARENT-SPECIFIC VIEWS - Using shared architecture
NO circular imports, PROPER service usage, WELL LOGGED
"""
import logging
from typing import List, Dict, Any

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.apps import apps
from django.core.exceptions import PermissionDenied

# SHARED IMPORTS
from shared.decorators.permissions import require_role, require_school_context
from shared.constants import StatusChoices
from shared.utils import FieldMapper

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'students'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def _get_user_parent_profiles(user) -> List[Any]:
    """Get all parent profiles for a user across all schools."""
    try:
        Profile = _get_model('Profile', 'users')
        parent_profiles = Profile.objects.filter(
            user=user, 
            role__system_role_type='parent'
        ).select_related('parent_profile', 'school')
        return list(parent_profiles)
    except Exception as e:
        logger.error(f"Error getting parent profiles for user {user.id}: {e}")
        return []


def _verify_parent_access(user, parent_instance) -> bool:
    """Verify that user has access to this parent profile."""
    parent_profiles = _get_user_parent_profiles(user)
    return any(profile.parent_profile == parent_instance for profile in parent_profiles)


# ============ PARENT DASHBOARD VIEWS ============

@login_required
def parent_dashboard_view(request):
    """
    Comprehensive parent dashboard showing all children and school-related info.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            logger.info(f"No parent profiles found for user {request.user.email}")
            messages.info(request, "You don't have any parent profiles associated with your account.")
            return render(request, 'students/parent_dashboard.html', {
                'children_data': [],
                'recent_invoices': [],
                'total_pending_fees': 0,
                'total_paid_fees': 0,
                'parent_count': 0,
                'children_count': 0,
            })
        
        children_data = []
        total_pending_fees = 0
        total_paid_fees = 0
        
        # Get models lazily
        Student = _get_model('Student')
        Invoice = _get_model('Invoice', 'billing')
        Application = _get_model('Application', 'admissions')
        Admission = _get_model('Admission', 'admissions')
        
        for profile in parent_profiles:
            parent = profile.parent_profile
            
            # Get all children for this parent
            children = Student.objects.filter(
                parent=parent, 
                is_active=True
            ).select_related('school', 'education_level', 'current_class')
            
            for child in children:
                # Get pending invoices for this child
                pending_invoices = Invoice.objects.filter(
                    student=child,
                    status__in=['sent', 'overdue']
                )
                
                # Get paid invoices for this child
                paid_invoices = Invoice.objects.filter(
                    student=child,
                    status=StatusChoices.PAID  # ✅ Use shared constant
                )
                
                # Get applications for this child
                applications = Application.objects.filter(
                    student=child
                ).select_related('form').order_by('-submitted_at')
                
                # Get admissions for this child
                admissions = Admission.objects.filter(
                    student=child
                ).select_related('offered_class').order_by('-created_at')
                
                child_pending = sum(inv.total_amount for inv in pending_invoices)
                child_paid = sum(inv.total_amount for inv in paid_invoices)
                
                total_pending_fees += child_pending
                total_paid_fees += child_paid
                
                children_data.append({
                    'child': child,
                    'school': child.school,
                    'current_class': child.current_class,  # ✅ Use current_class, not class_group
                    'pending_invoices': pending_invoices,
                    'paid_invoices': paid_invoices,
                    'applications': applications,
                    'admissions': admissions,
                    'total_pending': child_pending,
                    'total_paid': child_paid,
                    'profile_id': profile.id,
                })
        
        # Sort by school then by child name
        children_data.sort(key=lambda x: (x['school'].name, x['child'].first_name))
        
        # Get recent invoices across all children
        recent_invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles]
        ).select_related('school', 'student').order_by('-created_at')[:10]
        
        context = {
            'children_data': children_data,
            'recent_invoices': recent_invoices,
            'total_pending_fees': total_pending_fees,
            'total_paid_fees': total_paid_fees,
            'parent_count': len(parent_profiles),
            'children_count': len(children_data),
        }
        
        logger.info(f"Parent dashboard accessed for user {request.user.email} - {len(children_data)} children")
        return render(request, 'students/parent_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Parent dashboard error for user {request.user.id}: {e}", exc_info=True)
        messages.error(request, "Error loading your dashboard. Please try again.")
        return render(request, 'students/parent_dashboard.html', {})


@login_required
def parent_children_view(request):
    """
    View focused on children management for parents.
    Shows detailed child information across all schools.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            messages.info(request, "You don't have any parent profiles.")
            return redirect('dashboard')
        
        children_data = []
        Student = _get_model('Student')
        Attendance = _get_model('Attendance')
        
        for profile in parent_profiles:
            parent = profile.parent_profile
            children = Student.objects.filter(
                parent=parent
            ).select_related('school', 'education_level', 'current_class').order_by('school__name', 'first_name')
            
            for child in children:
                # Get recent attendance (last 30 days)
                recent_attendance = Attendance.objects.filter(
                    student=child,
                    date__gte=timezone.now() - timezone.timedelta(days=30)
                ).order_by('-date')[:5]
                
                # Calculate attendance statistics
                attendance_stats = {
                    'present': recent_attendance.filter(status='present').count(),
                    'absent': recent_attendance.filter(status='absent').count(),
                    'late': recent_attendance.filter(status='late').count(),
                }
                
                children_data.append({
                    'child': child,
                    'school': child.school,
                    'current_class': child.current_class,
                    'recent_attendance': recent_attendance,
                    'attendance_stats': attendance_stats,
                    'is_active': child.is_active,
                    'profile_id': profile.id,
                })
        
        context = {
            'children_data': children_data,
        }
        
        return render(request, 'students/parent_children.html', context)
        
    except Exception as e:
        logger.error(f"Parent children view error: {e}", exc_info=True)
        messages.error(request, "Error loading children information.")
        return redirect('students:parent_dashboard')


# ============ APPLICATION MANAGEMENT VIEWS ============

@login_required
def parent_applications_view(request):
    """
    View for parents to see their children's applications across all schools.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            messages.info(request, "You don't have any parent profiles.")
            return redirect('dashboard')
        
        # Get applications using service if available, otherwise direct query
        try:
            # Try to use ApplicationService if it exists
            from admissions.services import ApplicationService
            all_applications = []
            for profile in parent_profiles:
                parent = profile.parent_profile
                applications = ApplicationService.get_parent_applications(parent)
                all_applications.extend(applications)
        except ImportError:
            # Fall back to direct query
            Application = _get_model('Application', 'admissions')
            all_applications = Application.objects.filter(
                parent__in=[p.parent_profile for p in parent_profiles]
            ).select_related('student', 'form', 'admission').order_by('-submitted_at')
        
        # Group applications by status
        applications_by_status = {
            'pending': [],
            'under_review': [],
            'approved': [],
            'rejected': [],
        }
        
        for app in all_applications:
            if app.status == StatusChoices.PENDING:
                applications_by_status['pending'].append(app)
            elif app.status == 'under_review':
                applications_by_status['under_review'].append(app)
            elif app.status == StatusChoices.APPROVED:
                applications_by_status['approved'].append(app)
            elif app.status == StatusChoices.REJECTED:
                applications_by_status['rejected'].append(app)
        
        context = {
            'all_applications': all_applications,
            'applications_by_status': applications_by_status,
            'pending_count': len(applications_by_status['pending']),
            'approved_count': len(applications_by_status['approved']),
            'rejected_count': len(applications_by_status['rejected']),
        }
        
        logger.info(f"Parent applications viewed by user {request.user.email} - {len(all_applications)} applications")
        return render(request, 'students/parent_applications.html', context)
        
    except Exception as e:
        logger.error(f"Parent applications view error: {e}", exc_info=True)
        messages.error(request, "Error loading applications.")
        return redirect('students:parent_dashboard')


@login_required
def parent_application_detail_view(request, application_id):
    """
    Parent view of specific application details with enhanced information.
    """
    try:
        Application = _get_model('Application', 'admissions')
        
        application = get_object_or_404(
            Application.objects.select_related(
                'student', 'form', 'admission', 'parent'
            ),
            id=application_id
        )
        
        # Verify the parent owns this application
        if not _verify_parent_access(request.user, application.parent):
            logger.warning(f"Unauthorized access attempt to application {application_id} by user {request.user.id}")
            messages.error(request, "You don't have permission to view this application.")
            return redirect('students:parent_applications')
        
        # Get related data
        Invoice = _get_model('Invoice', 'billing')
        invoices = Invoice.objects.filter(
            application=application
        ).order_by('-created_at')
        
        # Get status history if available
        try:
            StatusHistory = _get_model('StatusHistory', 'admissions')
            status_history = StatusHistory.objects.filter(
                application=application
            ).select_related('changed_by').order_by('-changed_at')
        except LookupError:
            status_history = []
        
        context = {
            'application': application,
            'student': application.student,
            'invoices': invoices,
            'status_history': status_history,
            'can_pay': any(inv.status in ['sent', 'overdue'] for inv in invoices),
            'total_paid': sum(inv.amount_paid for inv in invoices if inv.status == StatusChoices.PAID),
            'total_due': sum(inv.total_amount for inv in invoices if inv.status in ['sent', 'overdue']),
        }
        
        return render(request, 'students/parent_application_detail.html', context)
        
    except Exception as e:
        logger.error(f"Parent application detail error: {e}", exc_info=True)
        messages.error(request, "Error loading application details.")
        return redirect('students:parent_applications')


# ============ PAYMENT VIEWS ============

@login_required
def parent_payment_view(request):
    """
    Unified payment page for parents across all schools and children.
    Shows all pending invoices with payment options.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            messages.info(request, "You don't have any parent profiles.")
            return redirect('dashboard')
        
        Invoice = _get_model('Invoice', 'billing')
        
        # Get all pending invoices across all schools and children
        pending_invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles],
            status__in=['sent', 'overdue']
        ).select_related('student', 'school', 'current_class').order_by('school__name', 'student__first_name')
        
        if not pending_invoices:
            messages.info(request, "You don't have any pending payments.")
            return redirect('students:parent_dashboard')
        
        # Group by school for better organization
        invoices_by_school = {}
        total_amount = 0
        
        for invoice in pending_invoices:
            school_name = invoice.school.name
            if school_name not in invoices_by_school:
                invoices_by_school[school_name] = {
                    'school': invoice.school,
                    'invoices': [],
                    'total': 0,
                }
            
            invoices_by_school[school_name]['invoices'].append(invoice)
            invoices_by_school[school_name]['total'] += invoice.total_amount
            total_amount += invoice.total_amount
        
        if request.method == 'POST':
            # Handle payment initialization
            selected_invoices = request.POST.getlist('selected_invoices')
            
            if not selected_invoices:
                messages.error(request, "Please select at least one invoice to pay.")
                return redirect('students:parent_payment')
            
            try:
                selected_invoices = Invoice.objects.filter(
                    id__in=selected_invoices,
                    parent__in=[p.parent_profile for p in parent_profiles]
                )
                
                if len(selected_invoices) == 1:
                    # Single invoice payment
                    invoice = selected_invoices.first()
                    try:
                        # Try to use PaymentService if available
                        from billing.services import PaymentService
                        payment_data = PaymentService.initialize_payment(
                            invoice=invoice,
                            email=request.user.email,
                            metadata={'invoice_id': invoice.id}
                        )
                        return redirect(payment_data['authorization_url'])
                    except ImportError:
                        # Fallback to direct Paystack integration
                        messages.error(request, "Payment service is currently unavailable.")
                        logger.error("PaymentService not found")
                
                else:
                    # Multiple invoices - combine amounts
                    total_selected = sum(inv.total_amount for inv in selected_invoices)
                    invoice_ids = ','.join(str(i.id) for i in selected_invoices)
                    
                    messages.info(request, 
                        f"Processing combined payment of ₦{total_selected:,.2f} for {len(selected_invoices)} invoices."
                    )
                    # Store selected invoices in session for combined payment
                    request.session['selected_invoice_ids'] = invoice_ids
                    return redirect('billing:combined_payment')
                    
            except Exception as e:
                logger.error(f"Payment initialization error: {e}", exc_info=True)
                messages.error(request, f"Error initializing payment: {str(e)}")
        
        context = {
            'invoices_by_school': invoices_by_school,
            'total_amount': total_amount,
            'pending_invoices': pending_invoices,
            'has_multiple_schools': len(invoices_by_school) > 1,
        }
        
        return render(request, 'students/parent_payment.html', context)
        
    except Exception as e:
        logger.error(f"Parent payment view error: {e}", exc_info=True)
        messages.error(request, "Error loading payment information.")
        return redirect('students:parent_dashboard')


# ============ SCHOOL-SPECIFIC PARENT VIEWS ============

@login_required
@require_school_context
def parent_school_dashboard_view(request):
    """
    Parent dashboard for a specific school.
    Shows children, invoices, and applications for the current school only.
    """
    try:
        school = request.school
        
        # Get parent profile for this school
        Profile = _get_model('Profile', 'users')
        profile = get_object_or_404(
            Profile.objects.select_related('parent_profile'),
            user=request.user,
            school=school,
            role__system_role_type='parent'
        )
        
        parent = profile.parent_profile
        
        # Get children in this school
        Student = _get_model('Student')
        children = Student.objects.filter(
            parent=parent,
            school=school,
            is_active=True
        ).select_related('education_level', 'current_class')
        
        # Get pending invoices for this school
        Invoice = _get_model('Invoice', 'billing')
        pending_invoices = Invoice.objects.filter(
            parent=parent,
            school=school,
            status__in=['sent', 'overdue']
        ).select_related('student')
        
        # Get recent applications for this school
        Application = _get_model('Application', 'admissions')
        recent_applications = Application.objects.filter(
            parent=parent,
            school=school
        ).select_related('student', 'form').order_by('-submitted_at')[:5]
        
        # Get attendance for children in this school
        Attendance = _get_model('Attendance')
        recent_attendance = []
        for child in children:
            attendance = Attendance.objects.filter(
                student=child
            ).order_by('-date')[:3]
            recent_attendance.extend(attendance)
        
        # Sort by date
        recent_attendance.sort(key=lambda x: x.date, reverse=True)
        
        context = {
            'school': school,
            'parent': parent,
            'children': children,
            'pending_invoices': pending_invoices,
            'recent_applications': recent_applications,
            'recent_attendance': recent_attendance[:10],  # Limit to 10 most recent
            'total_pending': sum(inv.total_amount for inv in pending_invoices),
            'children_count': children.count(),
        }
        
        return render(request, 'students/parent_school_dashboard.html', context)
        
    except Profile.DoesNotExist:
        messages.error(request, "You don't have a parent profile for this school.")
        return redirect('users:school_list')
    except Exception as e:
        logger.error(f"Parent school dashboard error: {e}", exc_info=True)
        messages.error(request, "Error loading school dashboard.")
        return redirect('users:school_list')


# ============ HTMX PARTIAL VIEWS ============

@login_required
def parent_invoices_partial(request):
    """
    HTMX endpoint for parent invoices table.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            return render(request, 'students/partials/empty_state.html', {
                'message': 'No parent profiles found'
            })
        
        Invoice = _get_model('Invoice', 'billing')
        
        # Get filter parameters
        status_filter = request.GET.get('status', 'pending')
        school_filter = request.GET.get('school', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        
        invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles]
        ).select_related('student', 'school')
        
        # Apply filters
        if status_filter == 'pending':
            invoices = invoices.filter(status__in=['sent', 'overdue'])
        elif status_filter == 'paid':
            invoices = invoices.filter(status=StatusChoices.PAID)
        
        if school_filter:
            invoices = invoices.filter(school_id=school_filter)
        
        if date_from:
            invoices = invoices.filter(created_at__gte=date_from)
        
        if date_to:
            invoices = invoices.filter(created_at__lte=date_to)
        
        # Order and paginate
        invoices = invoices.order_by('-created_at')[:50]
        
        return render(request, 'students/partials/parent_invoices.html', {
            'invoices': invoices,
            'status_filter': status_filter,
            'school_filter': school_filter,
        })
        
    except Exception as e:
        logger.error(f"Parent invoices partial error: {e}")
        return render(request, 'students/partials/error.html', {
            'message': 'Error loading invoices'
        })


@login_required
def parent_children_partial(request):
    """
    HTMX endpoint for parent children list.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            return render(request, 'students/partials/empty_state.html', {
                'message': 'No children found'
            })
        
        Student = _get_model('Student')
        children = Student.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles],
            is_active=True
        ).select_related('school', 'current_class', 'education_level').order_by('school__name', 'first_name')
        
        # Filter by school if provided
        school_filter = request.GET.get('school', '')
        if school_filter:
            children = children.filter(school_id=school_filter)
        
        return render(request, 'students/partials/parent_children.html', {
            'children': children,
            'school_filter': school_filter,
        })
        
    except Exception as e:
        logger.error(f"Parent children partial error: {e}")
        return render(request, 'students/partials/error.html', {
            'message': 'Error loading children'
        })


# ============ AJAX ENDPOINTS ============

@login_required
def parent_stats_ajax(request):
    """
    AJAX endpoint for parent dashboard statistics.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        if not parent_profiles:
            return JsonResponse({
                'children_count': 0,
                'pending_invoices': 0,
                'total_pending': 0,
                'schools_count': 0,
            })
        
        Student = _get_model('Student')
        Invoice = _get_model('Invoice', 'billing')
        
        children_count = Student.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles],
            is_active=True
        ).count()
        
        pending_invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles],
            status__in=['sent', 'overdue']
        )
        
        total_pending = sum(inv.total_amount for inv in pending_invoices)
        
        # Count unique schools
        schools_count = len(set(p.school_id for p in parent_profiles))
        
        return JsonResponse({
            'children_count': children_count,
            'pending_invoices_count': pending_invoices.count(),
            'total_pending': float(total_pending),
            'schools_count': schools_count,
            'status': 'success',
        })
        
    except Exception as e:
        logger.error(f"Parent stats AJAX error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error loading statistics',
        }, status=500)


@login_required
def parent_notifications_ajax(request):
    """
    AJAX endpoint for parent notifications.
    """
    try:
        parent_profiles = _get_user_parent_profiles(request.user)
        
        notifications = []
        
        if parent_profiles:
            # Get overdue invoices
            Invoice = _get_model('Invoice', 'billing')
            overdue_invoices = Invoice.objects.filter(
                parent__in=[p.parent_profile for p in parent_profiles],
                status='overdue'
            )[:5]
            
            for invoice in overdue_invoices:
                notifications.append({
                    'type': 'overdue',
                    'message': f'Overdue invoice for {invoice.student.full_name}: ₦{invoice.total_amount:,.2f}',
                    'url': invoice.get_absolute_url(),
                    'timestamp': invoice.due_date.isoformat(),
                })
            
            # Get upcoming events (placeholder - integrate with calendar)
            # Add calendar integration here
            
        return JsonResponse({
            'notifications': notifications,
            'unread_count': len(notifications),
            'status': 'success',
        })
        
    except Exception as e:
        logger.error(f"Parent notifications AJAX error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error loading notifications',
        }, status=500) 