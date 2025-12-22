# admissions/views.py
"""
CLEAN ADMISSIONS VIEWS - Using shared architecture and updated services
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
from django.db.models import Q, Count, Sum, F
from django.urls import reverse
from decimal import Decimal

# SHARED IMPORTS
from shared.decorators.permissions import require_school_context 
from shared.decorators.permissions import require_role

# LOCAL IMPORTS
from .models import ApplicationForm, Application, Admission
from .services import ApplicationService, AdmissionService
from students.models import Parent, Student
from users.models import Staff

logger = logging.getLogger(__name__)


# ============ PUBLIC APPLICATION VIEWS ============

# ============ PUBLIC APPLICATION VIEWS ============

def application_start_view(request, form_slug):
    """
    Landing/introduction page for application form.
    Shows form details before starting actual application.
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
        
        # Check existing application for logged-in users
        existing_application = None
        if request.user.is_authenticated:
            existing_application = Application.objects.filter(
                form=form,
                parent__user=request.user,
                status__in=['submitted', 'under_review', 'waitlisted']
            ).first()
        
        # Get available classes
        available_classes = form.available_classes if hasattr(form, 'available_classes') else []
        
        # Add capacity info to classes if available
        for class_obj in available_classes:
            try:
                class_obj.student_count = class_obj.students.count()
                class_obj.capacity = getattr(class_obj, 'capacity', 9999)
                class_obj.is_full = class_obj.student_count >= class_obj.capacity
            except:
                class_obj.student_count = 0
                class_obj.capacity = 9999
                class_obj.is_full = False
        
        context = {
            'form': form,
            'school': form.school,
            'available_classes': available_classes,
            'existing_application': existing_application,
            'today': timezone.now().date(),
            'page_title': f'Apply to {form.school.name}',
        }
        
        return render(request, 'admissions/public_application_start.html', context)
        
    except Exception as e:
        logger.error(f"Application start page error: {e}", exc_info=True)
        messages.error(request, "Error loading application information.")
        return redirect('school_discovery')


def apply_view(request, form_slug):
    """
    Main application form with payment flow.
    Users should come from application_start_view.
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
        
        # Check if user is authenticated
        if not request.user.is_authenticated:
            messages.info(request, "Please log in to start your application.")
            return redirect('account_login') + f'?next={reverse("admissions:apply", args=[form.slug])}'
        
        # Check for existing application
        existing_application = Application.objects.filter(
            form=form,
            parent__user=request.user,
            status__in=['submitted', 'under_review', 'waitlisted']
        ).first()
        
        if existing_application:
            messages.info(request, f"You already have an existing application: {existing_application.application_number}")
            return redirect('admissions:application_detail', application_id=existing_application.id)
        
        # Handle form submission
        if request.method == 'POST':
            return _handle_application_submission(request, form)
        
        # Show application form
        return _render_application_form(request, form)
        
    except Exception as e:
        logger.error(f"Application view error: {e}", exc_info=True)
        messages.error(request, "Error loading application form.")
        return redirect('admissions:application_start', form_slug=form_slug)




def _handle_application_submission(request, form):
    """Process application form submission using shared services."""
    try:
        # 1. Collect application data
        application_data = _extract_application_data(request)
        
        # 2. Submit application using ApplicationService
        result = ApplicationService.submit_application(
            application_data=application_data,
            form_slug=form.slug,
            user=request.user if request.user.is_authenticated else None,
            request=request
        )
        
        # 3. Handle response based on result
        if isinstance(result, dict) and result.get('requires_payment'):
            # Payment required - redirect to payment
            return _render_payment_redirect(request, result, form)
        elif isinstance(result, Application):
            # Application created successfully
            return _render_application_success(request, result, form)
        else:
            # Unexpected result
            raise ValidationError("Unexpected response from application service")
            
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
            'phone_number': request.POST.get('parent_phone', '').strip(),  # Alias for mapping
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
            'class': request.POST.get('class'),  # Class ID
        }
    }


def _render_application_form(request, form):
    """Render the application form."""
    # Get available classes for this form
    available_classes = form.available_classes if hasattr(form, 'available_classes') else []
    
    context = {
        'form': form,
        'school': form.school,
        'available_classes': available_classes,
        'today': timezone.now().date(),
        'page_title': f'Apply to {form.school.name}',
    }
    
    return render(request, 'admissions/apply.html', context)


def _render_payment_redirect(request, payment_result, form):
    """Render payment redirect page."""
    payment_data = payment_result.get('payment_data', {})
    invoice = payment_result.get('invoice')
    
    return render(request, 'admissions/payment_redirect.html', {
        'payment_url': payment_data.get('authorization_url', '#'),
        'reference': payment_data.get('reference', ''),
        'amount': payment_data.get('amount', 0),
        'invoice': invoice,
        'form': form,
        'school': form.school,
        'page_title': 'Complete Payment',
    })


def _render_application_success(request, application, form=None):
    """Render success page for application."""
    if form is None:
        form = application.form
    
    messages.success(request, 
        f"Application submitted successfully! Your application number is {application.application_number}"
    )
    
    return render(request, 'admissions/application_success.html', {
        'application': application,
        'school': form.school,
        'form': form,
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
        # Complete application using ApplicationService
        application = ApplicationService.complete_application_after_payment(reference)
        
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
        
        # Log webhook for debugging
        logger.info(f"Payment webhook received: {webhook_data}")
        
        # Extract reference from webhook data
        reference = webhook_data.get('reference') or webhook_data.get('data', {}).get('reference')
        
        if not reference:
            return JsonResponse({'error': 'No reference provided in webhook'}, status=400)
        
        # Process payment completion
        try:
            application = ApplicationService.complete_application_after_payment(reference)
            logger.info(f"Webhook processed successfully for reference: {reference}")
            return JsonResponse({'status': 'success', 'application_number': application.application_number}, status=200)
        except Exception as e:
            logger.error(f"Failed to process webhook for {reference}: {e}")
            return JsonResponse({'error': 'Failed to process payment'}, status=400)
            
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
        # Use shared paystack service or fallback
        try:
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
            
        except ImportError:
            # Fallback: redirect to application form with payment reminder
            messages.warning(request, "Payment gateway not available. Please contact support.")
            return redirect('admissions:apply', form_slug=application.form.slug)
        
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
        # Try to use shared payment service first
        try:
            from shared.services.payment.payment_core import PaymentCoreService
            PaymentCoreService.mark_paid(
                application.application_fee_invoice,
                payment_method='waiver',
                reference=f"WAIVER-{application.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                notes=f"Fee waived by {request.user.get_full_name()}"
            )
        except (ImportError, AttributeError):
            # Fallback: update invoice directly if exists
            if application.application_fee_invoice:
                invoice = application.application_fee_invoice
                invoice.payment_status = 'paid'
                invoice.payment_method = 'waiver'
                invoice.paid_at = timezone.now()
                invoice.notes = f"Fee waived by {request.user.get_full_name()}"
                invoice.save()
        
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


# ============ APPLICATION MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_admissions')
def admissions_dashboard_view(request):
    """Admissions dashboard for school administrators."""
    school = request.school
    
    try:
        # Get admission statistics using AdmissionService
        admission_stats = AdmissionService.get_admission_stats(school)
        
        # Recent applications
        recent_applications = Application.objects.filter(
            form__school=school
        ).select_related('student', 'parent', 'form').order_by('-submitted_at')[:10]
        
        # Application status breakdown
        status_breakdown = Application.objects.filter(
            form__school=school
        ).values('status').annotate(count=Count('id')).order_by('status')
        
        # Quick stats for dashboard cards
        quick_stats = {
            'total_revenue': Application.objects.filter(
                form__school=school,
                application_fee_paid=True
            ).aggregate(
                total=Sum('form__application_fee')
            )['total'] or 0,
            
            'avg_processing_time': Application.objects.filter(
                form__school=school,
                status='accepted'
            ).aggregate(
                avg_time=Avg(F('reviewed_at') - F('submitted_at'))
            )['avg_time'] or 0,
        }
        
        context = {
            'admission_stats': admission_stats,
            'quick_stats': quick_stats,
            'recent_applications': recent_applications,
            'status_breakdown': status_breakdown,
            'school': school,
            'page_title': 'Admissions Dashboard',
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
        priority_filter = request.GET.get('priority', '')
        
        if status_filter:
            applications = applications.filter(status=status_filter)
        if form_filter:
            applications = applications.filter(form_id=form_filter)
        if priority_filter:
            applications = applications.filter(priority=priority_filter)
        if search_query:
            applications = applications.filter(
                Q(application_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(parent__first_name__icontains=search_query) |
                Q(parent__last_name__icontains=search_query) |
                Q(parent__email__icontains=search_query) |
                Q(parent__phone_number__icontains=search_query)
            )
        
        # Get available forms for filter
        forms = ApplicationForm.objects.filter(school=school, status='active')
        
        # Pagination
        paginator = Paginator(applications, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Status counts for filter display
        status_counts = Application.objects.filter(
            form__school=school
        ).values('status').annotate(count=Count('id'))
        
        context = {
            'applications': page_obj,
            'forms': forms,
            'status_filter': status_filter,
            'form_filter': form_filter,
            'priority_filter': priority_filter,
            'search_query': search_query,
            'status_counts': status_counts,
            'page_obj': page_obj,
            'page_title': 'Applications List',
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
    application = get_object_or_404(
        Application.objects.select_related(
            'student', 'parent', 'form', 'assigned_to', 'applied_class'
        ),
        id=application_id,
        form__school=school
    )
    
    try:
        if request.method == 'POST':
            action = request.POST.get('action')
            notes = request.POST.get('review_notes', '')
            
            if action == 'assign_to_me':
                if request.user.staff_profile:
                    application.assigned_to = request.user.staff_profile
                    application.save()
                    messages.success(request, "Application assigned to you.")
                else:
                    messages.error(request, "You don't have a staff profile.")
                    
            elif action in ['accept', 'reject', 'waitlist']:
                application.status = action
                application.review_notes = notes
                application.reviewed_at = timezone.now()
                application.assigned_to = request.user.staff_profile if request.user.staff_profile else None
                application.save()
                
                if action == 'accept':
                    # Create admission offer
                    try:
                        admission = AdmissionService.process_application_acceptance(
                            application, request.user.staff_profile
                        )
                        messages.success(request, f"Application accepted! Admission {admission.admission_number} created.")
                    except Exception as e:
                        messages.error(request, f"Error creating admission: {str(e)}")
                else:
                    status_display = 'waitlisted' if action == 'waitlist' else action + 'ed'
                    messages.success(request, f"Application {status_display}.")
            
            return redirect('admissions:application_detail', application_id=application.id)
        
        # Get admission if exists
        admission = None
        try:
            admission = Admission.objects.get(application=application)
        except Admission.DoesNotExist:
            pass
        
        context = {
            'application': application,
            'admission': admission,
            'page_title': f'Application {application.application_number}',
        }
        
        return render(request, 'admissions/application_detail.html', context)
        
    except Exception as e:
        logger.error(f"Application detail error for application {application_id}: {str(e)}")
        messages.error(request, "Error processing application.")
        return redirect('admissions:application_list')


# ============ ADMISSION MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_admissions')
def admission_list_view(request):
    """List all admissions for the school."""
    school = request.school
    
    try:
        admissions = Admission.objects.filter(
            student__school=school
        ).select_related('student', 'application', 'offered_class', 'created_by').order_by('-created_at')
        
        # Filters
        status_filter = request.GET.get('status', '')
        class_filter = request.GET.get('class', '')
        search_query = request.GET.get('search', '')
        
        if status_filter == 'pending':
            admissions = admissions.filter(enrollment_completed=False)
        elif status_filter == 'enrolled':
            admissions = admissions.filter(enrollment_completed=True)
        
        if class_filter:
            admissions = admissions.filter(offered_class_id=class_filter)
        
        if search_query:
            admissions = admissions.filter(
                Q(admission_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(application__application_number__icontains=search_query)
            )
        
        # Get available classes for filter
        from core.models import Class
        classes = Class.objects.filter(school=school).order_by('name')
        
        # Pagination
        paginator = Paginator(admissions, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'admissions': page_obj,
            'classes': classes,
            'status_filter': status_filter,
            'class_filter': class_filter,
            'search_query': search_query,
            'page_obj': page_obj,
            'page_title': 'Admissions List',
        }
        
        return render(request, 'admissions/admission_list.html', context)
        
    except Exception as e:
        logger.error(f"Admission list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading admissions. Please try again.")
        return redirect('admissions:dashboard')


@login_required
@require_school_context
@require_role('manage_admissions')
def admission_detail_view(request, admission_id):
    """View admission details and manage admission."""
    school = request.school
    admission = get_object_or_404(
        Admission.objects.select_related(
            'student', 'application', 'offered_class', 'created_by'
        ),
        id=admission_id,
        student__school=school
    )
    
    try:
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'complete_enrollment':
                parent_notes = request.POST.get('parent_notes', '')
                
                try:
                    admission = AdmissionService.complete_enrollment(admission, parent_notes)
                    messages.success(request, "Enrollment completed successfully!")
                except ValidationError as e:
                    messages.error(request, str(e))
                
            elif action == 'resend_letter':
                method = request.POST.get('method', 'email')
                admission.send_admission_letter(method=method)
                messages.success(request, f"Admission letter sent via {method}.")
            
            return redirect('admissions:admission_detail', admission_id=admission.id)
        
        context = {
            'admission': admission,
            'page_title': f'Admission {admission.admission_number}',
        }
        
        return render(request, 'admissions/admission_detail.html', context)
        
    except Exception as e:
        logger.error(f"Admission detail error for admission {admission_id}: {str(e)}")
        messages.error(request, "Error processing admission.")
        return redirect('admissions:admission_list')
        
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
            ),
            public_uuid=application_uuid
        )
        
        # Check if admission exists
        admission = None
        try:
            admission = Admission.objects.get(application=application)
        except Admission.DoesNotExist:
            pass
        
        context = {
            'application': application,
            'admission': admission,
            'school': application.form.school,
            'page_title': 'Application Status',
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
        application = get_object_or_404(
            Application.objects.select_related('form__school', 'student', 'parent'),
            public_uuid=public_uuid
        )
        
        # Security check - only application owner or school staff can view
        if request.user.is_authenticated:
            if request.user != application.parent.user:
                # Check if user is staff at this school
                is_staff = Staff.objects.filter(
                    user=request.user,
                    school=application.form.school,
                    is_active=True
                ).exists()
                
                if not is_staff:
                    raise PermissionDenied
        # Allow unauthenticated access if they have the UUID (public view)
        
        context = {
            'application': application,
            'form': application.form,
            'school': application.form.school,
            'student': application.student,
            'parent': application.parent,
            'has_fee': bool(application.application_fee_invoice),
            'invoice': application.application_fee_invoice,
            'page_title': 'Application Submitted',
        }
        
        return render(request, 'admissions/application_success.html', context)
        
    except PermissionDenied:
        messages.error(request, "You don't have permission to view this application.")
        return redirect('users:dashboard')
    except Exception as e:
        logger.error(f"Error loading success page: {str(e)}")
        messages.error(request, "Error loading application details.")
        return redirect('school_discovery')


# ============ HTMX VIEWS ============

@login_required
@require_school_context
@require_role('manage_admissions')
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
        
        # Sort by priority and submission date
        applications = applications.order_by('-submitted_at')
        
        context = {
            'applications': applications[:20],  # Limit for partial view
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
                if request.user.staff_profile:
                    application.assigned_to = request.user.staff_profile
                    application.save()
                    return HttpResponse("✓ Assigned to you")
                else:
                    return HttpResponse("❌ No staff profile", status=400)
                    
            elif action == 'change_priority':
                new_priority = request.POST.get('priority')
                if new_priority in dict(Application.PRIORITY_CHOICES):
                    application.priority = new_priority
                    application.save()
                    return HttpResponse(f"✓ Priority: {new_priority.title()}")
                else:
                    return HttpResponse("❌ Invalid priority", status=400)
                    
            elif action == 'add_note':
                note = request.POST.get('note', '').strip()
                if note:
                    application.review_notes = note
                    application.save()
                    return HttpResponse("✓ Note added")
                else:
                    return HttpResponse("❌ Empty note", status=400)
                    
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


@login_required
@require_school_context
@require_role('manage_admissions')
def admission_stats_partial(request):
    """HTMX endpoint for admission statistics."""
    school = request.school
    
    try:
        stats = AdmissionService.get_admission_stats(school)
        
        return render(request, 'admissions/partials/admission_stats.html', {
            'stats': stats,
            'school': school,
        })
        
    except Exception as e:
        logger.error(f"Admission stats partial error: {str(e)}")
        return render(request, 'admissions/partials/error.html', {
            'message': 'Error loading statistics'
        })


@login_required
@require_school_context
@require_role('manage_admissions')
def payment_stats_partial(request):
    """HTMX endpoint for payment statistics."""
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
        
        'revenue_today': Application.objects.filter(
            form__school=school,
            application_fee_paid=True,
            submitted_at__date=timezone.now().date()
        ).aggregate(total=Sum('form__application_fee'))['total'] or 0,
    }
    
    return render(request, 'admissions/partials/payment_stats.html', {'stats': stats})