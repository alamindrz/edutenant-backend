# admissions/views.py
"""
CLEAN ADMISSIONS VIEWS - Using shared architecture
NO circular imports, NO ClassGroup references
"""
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.urls import reverse
from decimal import Decimal

# SHARED IMPORTS
from shared.decorators.permissions import require_school_context 
from shared.decorators.permissions import require_role
# FIXED: Correct import name
from shared.services.payment.application_fee import ApplicationPaymentService
# FIXED: Check if these imports exist, otherwise import from appropriate locations
try:
    from shared.models import ClassManager
except ImportError:
    # Fallback - define placeholder or import from correct location
    ClassManager = None

try:
    from shared.utils import FieldMapper
except ImportError:
    # Try alternative location
    try:
        from shared.utils.field_mapping import FieldMapper
    except ImportError:
        # Define minimal placeholder
        class FieldMapper:
            @staticmethod
            def map_form_to_model(data, model_type):
                # Simple passthrough if not available
                return data

# LOCAL IMPORTS ONLY
from .models import ApplicationForm, Application, Admission
from .services import ApplicationService
from students.models import Parent
from users.models import Staff

logger = logging.getLogger(__name__)


# ============ PUBLIC APPLICATION VIEWS ============


def apply_view(request, form_slug):
    """
    Clean application view with integrated payment flow using shared services.
    """
    try:
        form = get_object_or_404(
            ApplicationForm,
            slug=form_slug,
            status='active'
        )
        
        if not form.is_open:
            return render(request, 'admissions/application_closed.html', {
                'form': form,
                'school': form.school,
            })
        
        # Handle form submission
        if request.method == 'POST':
            return _handle_application_submission(request, form)
        
        # Show application form
        return _render_application_form(request, form)
        
    except Exception as e:
        logger.error(f"Application view error: {e}", exc_info=True)
        messages.error(request, "Error loading application form.")
        return redirect('school_discovery')


def _handle_application_submission(request, form):
    """Process application form submission using shared services."""
    try:
        # 1. Collect application data
        application_data = _extract_application_data(request)
        
        # 2. Map form fields using shared field mapper
        mapped_data = FieldMapper.map_form_to_model(application_data, 'application')
        
        # 3. Create application payment using shared service
        payment_data, invoice = ApplicationPaymentService.create_application_fee_invoice(
            parent_data=mapped_data.get('parent_data', {}),
            student_data=mapped_data.get('student_data', {}),
            form=form,
            user=request.user if request.user.is_authenticated else None
        )
        
        # 4. Handle response based on payment requirement
        if payment_data:
            # Payment required - redirect to payment
            return _render_payment_redirect(request, payment_data, invoice, form)
        elif invoice:
            # Zero amount (staff waiver) - show immediate success
            return _render_immediate_success(request, invoice, form)
        else:
            # Free application - show success
            return _render_free_application_success(request, mapped_data, form)
            
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect('admissions:apply', form_slug=form.slug)
    except Exception as e:
        logger.error(f"Application submission error: {e}", exc_info=True)
        messages.error(request, "An error occurred while submitting your application.")
        return redirect('admissions:apply', form_slug=form.slug)


def _extract_application_data(request):
    """Extract and validate application data from request."""
    return {
        'parent_data': {
            'first_name': request.POST.get('parent_first_name', '').strip(),
            'last_name': request.POST.get('parent_last_name', '').strip(),
            'email': request.POST.get('parent_email', '').strip().lower(),
            'phone': request.POST.get('parent_phone', '').strip(),
            'address': request.POST.get('parent_address', '').strip(),
            'relationship': request.POST.get('parent_relationship', 'Parent'),
        },
        'student_data': {
            'first_name': request.POST.get('student_first_name', '').strip(),
            'last_name': request.POST.get('student_last_name', '').strip(),
            'gender': request.POST.get('student_gender', ''),
            'date_of_birth': request.POST.get('student_dob', ''),
            'previous_school': request.POST.get('previous_school', '').strip(),
            'previous_class': request.POST.get('previous_class', '').strip(),
            'class': request.POST.get('class'),  # Use 'class' not 'class_group'
        }
    }


def _render_application_form(request, form):
    """Render the application form using shared ClassManager."""
    # Get available classes using shared manager or direct query
    if form.available_class_ids:
        from core.models import Class
        available_classes = Class.objects.filter(
            id__in=form.available_class_ids,
            school=form.school
        )
    else:
        # Fallback to direct query if ClassManager not available
        try:
            from core.models import Class
            available_classes = Class.objects.filter(school=form.school).order_by('name')
        except ImportError:
            available_classes = []
    
    context = {
        'form': form,
        'school': form.school,
        'available_classes': available_classes,
        'today': timezone.now().date(),
        'page_title': f'Apply to {form.school.name}',
    }
    
    return render(request, 'admissions/apply.html', context)


def _render_payment_redirect(request, payment_data, invoice, form):
    """Render payment redirect page."""
    return render(request, 'admissions/payment_redirect.html', {
        'payment_url': payment_data.get('authorization_url', '#'),
        'reference': payment_data.get('reference', ''),
        'amount': payment_data.get('amount', 0),
        'invoice': invoice,
        'form': form,
        'school': form.school,
        'page_title': 'Complete Payment',
    })


def _render_immediate_success(request, invoice, form):
    """Render success page for zero-amount applications (staff waivers)."""
    # For staff waivers, the application is already created by the service
    try:
        # The invoice metadata contains application data
        metadata = invoice.metadata or {}
        
        # Get the application that was created
        from admissions.models import Application
        application = Application.objects.filter(
            application_fee_invoice=invoice
        ).first()
        
        if not application:
            # Fallback: try to create application from metadata
            application = ApplicationService.submit_application(
                application_data=metadata.get('application_data', {}),
                form_slug=form.slug,
                user=request.user if request.user.is_authenticated else None,
                request=request
            )
        
        messages.success(request, 
            f"Application submitted successfully! Your application number is {application.application_number}"
        )
        
        return render(request, 'admissions/application_success.html', {
            'application': application,
            'school': form.school,
            'page_title': 'Application Submitted',
        })
        
    except Exception as e:
        logger.error(f"Failed to create application for waiver: {e}")
        messages.error(request, "Application submitted but encountered an error. Please contact support.")
        return redirect('admissions:apply', form_slug=form.slug)


def _render_free_application_success(request, mapped_data, form):
    """Render success page for free applications."""
    application = ApplicationService.submit_application(
        application_data=mapped_data,
        form_slug=form.slug,
        user=request.user if request.user.is_authenticated else None,
        request=request
    )
    
    messages.success(request, 
        f"Application submitted successfully! Your application number is {application.application_number}"
    )
    
    return render(request, 'admissions/application_success.html', {
        'application': application,
        'school': application.form.school,
        'page_title': 'Application Submitted',
    })


# ============ PAYMENT CALLBACK VIEWS ============


def payment_success_view(request):
    """
    Handle payment success callback using shared services.
    """
    reference = request.GET.get('reference', '')
    
    if not reference:
        messages.error(request, "No payment reference provided.")
        return redirect('school_discovery')
    
    try:
        # Complete application using shared service
        application = ApplicationPaymentService.complete_application_after_payment(reference)
        
        return render(request, 'admissions/payment_success.html', {
            'application': application,
            'school': application.form.school,
            'reference': reference,
            'page_title': 'Payment Successful',
        })
        
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect('school_discovery')
    except Exception as e:
        logger.error(f"Payment success error: {e}", exc_info=True)
        
        # Check if payment might still be processing
        error_str = str(e).lower()
        if "not found" in error_str or "verification" in error_str:
            return render(request, 'admissions/payment_pending.html', {
                'reference': reference,
                'page_title': 'Payment Processing',
            })
        
        messages.error(request, "An error occurred while processing your payment.")
        return redirect('school_discovery')


def payment_cancel_view(request):
    """
    Handle payment cancellation.
    """
    reference = request.GET.get('reference', '')
    
    if reference:
        messages.info(request, "Payment was cancelled. You can try again.")
    else:
        messages.info(request, "Payment was cancelled.")
    
    # Try to get the form slug from session or redirect to discovery
    form_slug = request.session.get('pending_form_slug')
    if form_slug:
        return redirect('admissions:apply', form_slug=form_slug)
    
    return redirect('school_discovery')


@csrf_exempt
@require_http_methods(["POST"])
def payment_webhook_view(request):
    """
    Handle payment webhooks for application fees.
    """
    try:
        # Get webhook data
        webhook_data = json.loads(request.body.decode('utf-8'))
        
        # Process using shared service
        success = ApplicationPaymentService.verify_and_process_payment_webhook(webhook_data)
        
        if success:
            return JsonResponse({'status': 'success'}, status=200)
        else:
            return JsonResponse({'error': 'Webhook processing failed'}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


# ============ PAYMENT MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_admissions')
def payment_monitoring_view(request):
    """
    Monitor pending payments and payment issues.
    """
    school = request.school
    
    # Get payment statistics
    stats = {
        'pending_payments': Application.objects.filter(
            form__school=school,
            status='submitted',
            application_fee_paid=False,
            application_fee_invoice__isnull=False
        ).count(),
        
        'failed_payments': Application.objects.filter(
            form__school=school,
            application_fee_invoice__payment_status='failed'
        ).count(),
        
        'today_successful': Application.objects.filter(
            form__school=school,
            application_fee_paid=True,
            submitted_at__date=timezone.now().date()
        ).count(),
        
        'conversion_rate': _calculate_payment_conversion_rate(school),
    }
    
    # Get pending applications with their invoices
    pending_applications = Application.objects.filter(
        form__school=school,
        status='submitted',
        application_fee_paid=False,
        application_fee_invoice__isnull=False
    ).select_related('parent', 'form', 'application_fee_invoice').order_by('-submitted_at')
    
    # Get failed payments
    failed_invoices = Application.objects.filter(
        form__school=school,
        application_fee_invoice__payment_status='failed'
    ).select_related('parent', 'form', 'application_fee_invoice').order_by('-submitted_at')
    
    context = {
        'stats': stats,
        'pending_applications': pending_applications,
        'failed_invoices': failed_invoices,
        'school': school,
        'page_title': 'Payment Monitoring',
    }
    
    return render(request, 'admissions/payment_monitoring.html', context)


def _calculate_payment_conversion_rate(school):
    """Calculate payment conversion rate."""
    total_applications = Application.objects.filter(form__school=school).count()
    paid_applications = Application.objects.filter(
        form__school=school,
        application_fee_paid=True
    ).count()
    
    if total_applications == 0:
        return 0
    
    return round((paid_applications / total_applications) * 100, 1)


@login_required
@require_school_context
@require_role('manage_admissions')
def retry_payment_view(request, application_id):
    """
    Allow retrying payment for pending applications.
    """
    application = get_object_or_404(
        Application,
        id=application_id,
        form__school=request.school,
        application_fee_paid=False
    )
    
    if not application.application_fee_invoice:
        messages.error(request, "No invoice found for this application.")
        return redirect('admissions:payment_monitoring')
    
    try:
        # Use shared paystack service
        from shared.services.payment.paystack import PaystackService
        paystack_service = PaystackService()
        
        payment_data = paystack_service.initialize_payment(
            invoice=application.application_fee_invoice,
            customer_email=application.parent.email,
            metadata={
                'application_id': application.id,
                'is_retry': True
            }
        )
        
        return render(request, 'admissions/payment_redirect.html', {
            'payment_url': payment_data['authorization_url'],
            'reference': payment_data['reference'],
            'amount': payment_data['amount'],
            'application': application,
            'form': application.form,
            'school': request.school,
            'is_retry': True,
            'page_title': 'Retry Payment',
        })
        
    except Exception as e:
        logger.error(f"Retry payment error: {e}")
        messages.error(request, f"Failed to initialize payment: {str(e)}")
        return redirect('admissions:payment_monitoring')


@login_required
@require_school_context
@require_role('manage_admissions')
def waive_application_fee_view(request, application_id):
    """
    Waive application fee (for staff or special cases).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    application = get_object_or_404(
        Application,
        id=application_id,
        form__school=request.school,
        application_fee_paid=False
    )
    
    try:
        # Mark invoice as paid using shared service
        if application.application_fee_invoice:
            from shared.services.payment.payment_core import PaymentCoreService
            PaymentCoreService.mark_paid(
                application.application_fee_invoice,
                payment_method='waiver',
                reference=f"WAIVER-{application.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                notes=f"Fee waived by {request.user.get_full_name()}"
            )
        
        # Update application
        application.application_fee_paid = True
        application.save(update_fields=['application_fee_paid'])
        
        messages.success(request, 
            f"Application fee waived for {application.application_number}"
        )
        
        if request.headers.get('HX-Request'):
            return render(request, 'admissions/partials/application_row.html', {
                'application': application
            })
        
        return redirect('admissions:payment_monitoring')
        
    except Exception as e:
        logger.error(f"Fee waiver error: {e}")
        messages.error(request, f"Error waiving fee: {str(e)}")
        return redirect('admissions:payment_monitoring')


@login_required
@require_school_context
@require_role('manage_admissions')
def payment_stats_partial(request):
    """
    HTMX endpoint for payment statistics.
    """
    school = request.school
    
    stats = {
        'pending_count': Application.objects.filter(
            form__school=school,
            application_fee_paid=False,
            application_fee_invoice__isnull=False
        ).count(),
        
        'conversion_rate': _calculate_payment_conversion_rate(school),
        
        'failed_today': Application.objects.filter(
            form__school=school,
            application_fee_invoice__payment_status='failed',
            submitted_at__date=timezone.now().date()
        ).count(),
    }
    
    return render(request, 'admissions/partials/payment_stats.html', {'stats': stats})


# ============ APPLICATION MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_admissions')
def admissions_dashboard_view(request):
    """Admissions dashboard for school administrators."""
    school = request.school
    
    try:
        # Admission statistics
        admission_stats = {
            'total_applications': Application.objects.filter(form__school=school).count(),
            'pending_review': Application.objects.filter(form__school=school, status='submitted').count(),
            'accepted': Application.objects.filter(form__school=school, status='accepted').count(),
            'admitted': Admission.objects.filter(student__school=school).count(),
        }
        
        # Recent applications
        recent_applications = Application.objects.filter(
            form__school=school
        ).select_related('student', 'parent', 'form').order_by('-submitted_at')[:10]
        
        # Application status breakdown
        status_breakdown = Application.objects.filter(
            form__school=school
        ).values('status').annotate(count=Count('id')).order_by('status')
        
        context = {
            'admission_stats': admission_stats,
            'recent_applications': recent_applications,
            'status_breakdown': status_breakdown,
            'school': school,
        }
        
        logger.info(f"Admissions dashboard accessed for school {school.name}")
        return render(request, 'admissions/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Admissions dashboard error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading admissions dashboard. Please try again.")
        return redirect('users:dashboard')


@login_required
@require_school_context
@require_role('manage_admissions')
def application_list_view(request):
    """List all applications for the school."""
    school = request.school
    
    try:
        applications = Application.objects.filter(
            form__school=school
        ).select_related('student', 'parent', 'form', 'assigned_to').order_by('-submitted_at')
        
        # Filters
        status_filter = request.GET.get('status', '')
        form_filter = request.GET.get('form', '')
        search_query = request.GET.get('search', '')
        
        if status_filter:
            applications = applications.filter(status=status_filter)
        if form_filter:
            applications = applications.filter(form_id=form_filter)
        if search_query:
            applications = applications.filter(
                Q(application_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(parent__first_name__icontains=search_query) |
                Q(parent__last_name__icontains=search_query)
            )
        
        # Get available forms for filter
        forms = ApplicationForm.objects.filter(school=school, status='active')
        
        # Pagination
        paginator = Paginator(applications, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'applications': page_obj,
            'forms': forms,
            'status_filter': status_filter,
            'form_filter': form_filter,
            'search_query': search_query,
            'page_obj': page_obj,
        }
        
        return render(request, 'admissions/application_list.html', context)
        
    except Exception as e:
        logger.error(f"Application list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading applications. Please try again.")
        return redirect('admissions:dashboard')


@login_required
@require_school_context
@require_role('manage_admissions')
def application_detail_view(request, application_id):
    """View application details and manage application."""
    school = request.school
    application = get_object_or_404(Application, id=application_id, form__school=school)
    
    try:
        if request.method == 'POST':
            action = request.POST.get('action')
            notes = request.POST.get('review_notes', '')
            
            if action == 'assign_to_me':
                application.assigned_to = request.user.staff_profile
                application.save()
                messages.success(request, "Application assigned to you.")
                
            elif action in ['accept', 'reject', 'waitlist']:
                application.status = action
                application.review_notes = notes
                application.reviewed_at = timezone.now()
                application.assigned_to = request.user.staff_profile
                application.save()
                
                if action == 'accept':
                    # Create admission offer
                    from admissions.services import AdmissionService
                    admission = AdmissionService.process_application_acceptance(
                        application, request.user.staff_profile
                    )
                    messages.success(request, f"Application accepted! Admission {admission.admission_number} created.")
                else:
                    messages.success(request, f"Application {action}ed.")
            
            return redirect('admissions:application_detail', application_id=application.id)
        
        context = {
            'application': application,
        }
        
        return render(request, 'admissions/application_detail.html', context)
        
    except Exception as e:
        logger.error(f"Application detail error for application {application_id}: {str(e)}")
        messages.error(request, "Error processing application.")
        return redirect('admissions:application_list')


# ============ PUBLIC VIEWS ============


def public_application_status_view(request, application_uuid):
    """
    Public view for checking application status using UUID.
    Accessible without login for parents to check their application status.
    """
    try:
        application = get_object_or_404(
            Application.objects.select_related(
                'form__school', 
                'student', 
                'parent',
                'applied_class',
                'admission'
            ),
            public_uuid=application_uuid
        )
        
        context = {
            'application': application,
            'school': application.form.school,
        }
        
        return render(request, 'admissions/public_application_status.html', context)
        
    except Application.DoesNotExist:
        return render(request, 'admissions/application_not_found.html', status=404)
    except Exception as e:
        logger.error(f"Public application status error: {str(e)}")
        return render(request, 'admissions/application_error.html', status=500)


def application_success_view(request, public_uuid):
    """Display application submission success page."""
    try:
        application = get_object_or_404(Application, public_uuid=public_uuid)
        
        # Security check - only application owner or school staff can view
        if request.user != application.parent.user:
            # Check if user is staff at this school
            is_staff = Staff.objects.filter(
                user=request.user,
                school=application.form.school,
                is_active=True
            ).exists()
            
            if not is_staff:
                raise PermissionDenied
        
        context = {
            'application': application,
            'form': application.form,
            'school': application.form.school,
            'student': application.student,
            'parent': application.parent,
            'has_fee': bool(application.application_fee_invoice),
            'invoice': application.application_fee_invoice,
        }
        
        return render(request, 'admissions/application_success.html', context)
        
    except PermissionDenied:
        messages.error(request, "You don't have permission to view this application.")
        return redirect('users:dashboard')
    except Exception as e:
        logger.error(f"Error loading success page: {str(e)}")
        messages.error(request, "Error loading application details.")
        return redirect('users:dashboard')


# ============ HTMX VIEWS ============

@login_required
@require_school_context
def application_table_partial(request):
    """HTMX endpoint for application table with filters."""
    school = request.school
    
    try:
        applications = Application.objects.filter(form__school=school).select_related('student', 'parent', 'form')
        
        # Apply filters
        status_filter = request.GET.get('status', '')
        form_filter = request.GET.get('form', '')
        search_query = request.GET.get('search', '')
        
        if status_filter:
            applications = applications.filter(status=status_filter)
        if form_filter:
            applications = applications.filter(form_id=form_filter)
        if search_query:
            applications = applications.filter(
                Q(application_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query)
            )
        
        context = {
            'applications': applications,
            'status_filter': status_filter,
            'form_filter': form_filter,
            'search_query': search_query,
        }
        
        return render(request, 'admissions/partials/application_table.html', context)
        
    except Exception as e:
        logger.error(f"Application table partial error: {str(e)}")
        return render(request, 'admissions/partials/error.html', {'message': 'Error loading applications'})
        

@login_required
@require_school_context
def application_quick_actions_view(request, application_id):
    """HTMX endpoint for quick application actions."""
    school = request.school
    application = get_object_or_404(Application, id=application_id, form__school=school)
    
    if request.method == 'POST' and request.headers.get('HX-Request'):
        action = request.POST.get('action')
        
        try:
            if action == 'assign_to_me':
                application.assigned_to = request.user.staff_profile
                application.save()
                return HttpResponse("✓ Assigned to you")
                
            elif action == 'change_priority':
                new_priority = request.POST.get('priority')
                if new_priority in dict(Application._meta.get_field('priority').choices):
                    application.priority = new_priority
                    application.save()
                    return HttpResponse(f"✓ Priority: {new_priority.title()}")
                    
            elif action == 'add_note':
                note = request.POST.get('note', '').strip()
                if note:
                    application.review_notes = note
                    application.save()
                    return HttpResponse("✓ Note added")
                    
        except Exception as e:
            logger.error(f"Quick action error: {str(e)}")
            return HttpResponse("❌ Error", status=400)
    
    return render(request, 'admissions/partials/quick_actions.html', {
        'application': application
    })


@login_required
@require_school_context
def application_filters_partial(request):
    """HTMX endpoint for dynamic application filters."""
    school = request.school
    
    status_counts = Application.objects.filter(
        form__school=school
    ).values('status').annotate(count=Count('id'))
    
    priority_counts = Application.objects.filter(
        form__school=school
    ).values('priority').annotate(count=Count('id'))
    
    return render(request, 'admissions/partials/filter_widgets.html', {
        'status_counts': status_counts,
        'priority_counts': priority_counts,
        'forms': ApplicationForm.objects.filter(school=school, status='active')
    })