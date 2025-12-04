# admissions/views.py
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Sum
from core.decorators import require_role, require_school_context
from .models import ApplicationForm, Application, Admission
from django.urls import reverse
from students.models import Student, Parent

from django.core.exceptions import ValidationError
from billing.services import BillingService
from .services import AdmissionService, ApplicationService
from django.http import Http404
from django.views.decorators.http import require_http_methods
logger = logging.getLogger(__name__)


from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from students.models import ClassGroup, EducationLevel



def validate_application_field_view(request, form_slug):
    """HTMX endpoint for real-time field validation."""
    try:
        field_name = request.GET.get('field')
        field_value = request.GET.get('value', '')
        
        validation_rules = {
            'parent_email': {
                'pattern': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
                'message': 'Please enter a valid email address'
            },
            'parent_phone': {
                'pattern': r'^\+?[\d\s-]{10,}$',
                'message': 'Please enter a valid phone number'
            },
            'student_dob': {
                'validator': lambda v: timezone.datetime.strptime(v, '%Y-%m-%d').date() < timezone.now().date(),
                'message': 'Date of birth cannot be in the future'
            }
        }
        
        if field_name in validation_rules:
            rule = validation_rules[field_name]
            
            if 'pattern' in rule:
                import re
                if not re.match(rule['pattern'], field_value):
                    return HttpResponse(f'<div class="text-danger small">{rule["message"]}</div>')
            
            if 'validator' in rule:
                if not rule['validator'](field_value):
                    return HttpResponse(f'<div class="text-danger small">{rule["message"]}</div>')
        
        return HttpResponse('<div class="text-success small"><i class="bi bi-check"></i> Valid</div>')
        
    except Exception as e:
        logger.error(f"Field validation error: {str(e)}")
        return HttpResponse('')


@login_required
@require_school_context
@require_role('manage_admissions')
def manage_application_forms_view(request):
    """Manage application forms for the school."""
    school = request.school
    
    try:
        application_forms = ApplicationForm.objects.filter(school=school).order_by('-created_at')
        
        # Pre-calculate counts for the template
        active_forms_count = application_forms.filter(status='active').count()
        draft_forms_count = application_forms.filter(status='draft').count()
        
        # Calculate total applications from active forms
        total_applications = application_forms.filter(status='active').aggregate(
            total=Sum('applications_so_far')
        )['total'] or 0
        
        if request.method == 'POST':
            action = request.POST.get('action')
            form_id = request.POST.get('form_id')
            
            if action == 'create_form':
                # Create new application form
                name = request.POST.get('name')
                academic_session = request.POST.get('academic_session')
                
                if not name or not academic_session:
                    messages.error(request, "Name and academic session are required.")
                else:
                    form = ApplicationForm.objects.create(
                        school=school,
                        name=name,
                        description=request.POST.get('description', ''),
                        academic_session=academic_session,
                        application_fee=request.POST.get('application_fee', 0) or 0,
                        open_date=request.POST.get('open_date') or timezone.now(),
                        close_date=request.POST.get('close_date') or (timezone.now() + timezone.timedelta(days=90)),
                        created_by=request.user
                    )
                    messages.success(request, f"Application form '{form.name}' created successfully!")
                
            elif action == 'toggle_status' and form_id:
                form = get_object_or_404(ApplicationForm, id=form_id, school=school)
                if form.status == 'active':
                    form.status = 'paused'
                else:
                    form.status = 'active'
                form.save()
                messages.success(request, f"Form '{form.name}' status updated to {form.status}")
            
            elif action == 'delete_form' and form_id:
                form = get_object_or_404(ApplicationForm, id=form_id, school=school)
                form_name = form.name
                form.delete()
                messages.success(request, f"Application form '{form_name}' deleted successfully!")
            
            return redirect('admissions:manage_application_forms')
        
        context = {
            'application_forms': application_forms,
            'active_forms_count': active_forms_count,
            'draft_forms_count': draft_forms_count,
            'total_applications': total_applications,
            'school': school,
            'today': timezone.now().date(),
        }
        
        return render(request, 'admissions/manage_application_forms.html', context)
        
    except Exception as e:
        logger.error(f"Application forms management error: {str(e)}")
        messages.error(request, "Error managing application forms.")
        return redirect('admissions:dashboard')

        
        
        
        
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

def application_update_view(request, application_id):
    """HTMX view to update application status."""
    if not request.htmx:
        return redirect('admissions:application_detail', application_id=application_id)
    
    application = get_object_or_404(StudentApplication, id=application_id, school=request.school)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        review_notes = request.POST.get('review_notes', '')
        
        if review_notes:
            application.review_notes = review_notes
        
        if action == 'accept':
            application.status = 'accepted'
        elif action == 'reject':
            application.status = 'rejected'
        elif action == 'waitlist':
            application.status = 'waitlisted'
        elif action == 'assign_to_me':
            application.assigned_to = request.user.staff_profile
        
        application.save()
        
        # Return just the updated header partial
        return render(request, 'admissions/partials/application_header.html', {
            'application': application
        })


@login_required
@require_school_context
def application_timeline_partial(request, application_id):
    """HTMX endpoint for application timeline updates."""
    school = request.school
    application = get_object_or_404(
        Application.objects.select_related('student', 'parent', 'form', 'assigned_to'),
        id=application_id, 
        form__school=school
    )
    
    return render(request, 'admissions/partials/application_timeline_partial.html', {
        'application': application
    })
    
    
    
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
            'scholarship_eligible': application.scholarship_eligible,
            'potential_scholarships': application.potential_scholarships or [],
        }
        
        return render(request, 'admissions/application_success.html', context)
        
    except Http404:
        messages.error(request, "Application not found.")
        return redirect('users:dashboard')
    except PermissionDenied:
        messages.error(request, "You don't have permission to view this application.")
        return redirect('users:dashboard')
    except Exception as e:
        logger.error(f"Error loading success page: {str(e)}")
        messages.error(request, "Error loading application details.")
        return redirect('users:dashboard')





def application_status_check_view(request, application_id):
    """
    HTMX endpoint for checking application status updates.
    """
    application = get_object_or_404(Application, id=application_id)
    
    # Verify permissions
    has_permission = False
    if request.user.is_authenticated:
        if hasattr(request.user, 'parent_profile') and application.parent == request.user.parent_profile:
            has_permission = True
        elif hasattr(request.user, 'staff_profile') and application.form.school == request.user.staff_profile.school:
            if request.user.staff_profile.has_perm('admissions.manage_admissions'):
                has_permission = True
    
    if not has_permission:
        return HttpResponse("Unauthorized", status=403)
    
    return render(request, 'admissions/partials/application_status_check.html', {
        'application': application
    })


def public_application_success_view(request, application_uuid):
    """
    Public success view that doesn't require login - uses UUID for security.
    """
    try:
        application = get_object_or_404(
            Application.objects.select_related('form__school', 'applied_class'),
            public_uuid=application_uuid  # You'll need to add this field to the model
        )
        
        context = {
            'application': application,
            'school': application.form.school,
        }
        
        return render(request, 'admissions/application_success.html', context)
        
    except Application.DoesNotExist:
        return render(request, 'admissions/application_not_found.html', status=404)




# In admissions/views.py - update the dashboard view
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
        
        # Get priority choices from the model
        priority_choices = Application.PRIORITY_CHOICES  # Make sure this exists in your model
        
        context = {
            'admission_stats': admission_stats,
            'recent_applications': recent_applications,
            'status_breakdown': status_breakdown,
            'priority_choices': priority_choices,  # Add this line
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
                application.assigned_to = request.user.profile_set.get(school=school)
                application.save()
                messages.success(request, "Application assigned to you.")
                
            elif action in ['accept', 'reject', 'waitlist']:
                application.status = action
                application.review_notes = notes
                application.reviewed_at = timezone.now()
                application.assigned_to = request.user.profile_set.get(school=school)
                application.save()
                
                if action == 'accept':
                    # Create admission offer
                    admission = Admission.objects.create(
                        application=application,
                        student=application.student,
                        offered_class=application.applied_class,
                        requires_acceptance_fee=application.form.has_acceptance_fee
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


@login_required
@require_school_context
@require_role('manage_admissions')
def admission_list_view(request):
    """List all admissions for the school."""
    school = request.school
    
    try:
        admissions = Admission.objects.filter(
            student__school=school
        ).select_related('student', 'application', 'offered_class').order_by('-offer_expires')
        
        # Filters
        status_filter = request.GET.get('status', 'all')
        search_query = request.GET.get('search', '')
        
        if status_filter == 'accepted':
            admissions = admissions.filter(accepted=True)
        elif status_filter == 'pending':
            admissions = admissions.filter(accepted=False, offer_expires__gt=timezone.now())
        elif status_filter == 'expired':
            admissions = admissions.filter(accepted=False, offer_expires__lte=timezone.now())
        
        if search_query:
            admissions = admissions.filter(
                Q(admission_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query)
            )
        
        context = {
            'admissions': admissions,
            'status_filter': status_filter,
            'search_query': search_query,
        }
        
        return render(request, 'admissions/admission_list.html', context)
        
    except Exception as e:
        logger.error(f"Admission list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading admissions. Please try again.")
        return redirect('admissions:dashboard')



def public_application_form_view(request, form_slug):
    """Public application form for parents."""
    try:
        application_form = get_object_or_404(
            ApplicationForm, 
            slug=form_slug,  # You'll need to add a slug field
            status='active'
        )
        
        if not application_form.is_open:
            return render(request, 'admissions/application_closed.html', {'form': application_form})
        
        if request.method == 'POST':
            # Process application form
            # This would handle the complex application submission process
            # Including creating student, parent, and application records
            
            messages.success(request, "Application submitted successfully! You will receive a confirmation email.")
            return redirect('admissions:application_success', form_slug=form_slug)
        
        context = {
            'form': application_form,
        }
        
        return render(request, 'admissions/public_application_form.html', context)
        
    except Exception as e:
        logger.error(f"Public application form error for form {form_slug}: {str(e)}")
        return render(request, 'admissions/application_error.html', status=500)


# HTMX Views
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
        
      


# Enhanced HTMX Views
@login_required
@require_school_context
@require_http_methods(["GET", "POST"])
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
                    # Store note in status_history or separate field
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

@login_required
@require_school_context
def admission_stats_partial(request):
    """HTMX endpoint for live admission statistics."""
    school = request.school
    stats = AdmissionService.get_admission_stats(school.id)
    
    return render(request, 'admissions/partials/stats_cards.html', {
        'admission_stats': stats
    })

# Enhanced Main Views
@login_required
@require_school_context
@require_role('manage_admissions')
def application_detail_view(request, application_id):
    """Enhanced application detail with HTMX components."""
    school = request.school
    application = get_object_or_404(
        Application.objects.select_related(
            'student', 'parent', 'form', 'assigned_to', 'applied_class'
        ).prefetch_related('application_fee_invoice'),
        id=application_id, form__school=school
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        try:
            if action == 'accept_application':
                # Use service for transaction safety
                admission = AdmissionService.process_application_acceptance(
                    application, request.user.staff_profile
                )
                messages.success(request, f"Application accepted! Admission {admission.admission_number} created.")
                
            elif action in ['reject', 'waitlist']:
                application.status = action
                application.review_notes = request.POST.get('review_notes', '')
                application.reviewed_at = timezone.now()
                application.assigned_to = request.user.staff_profile
                application.save()
                messages.success(request, f"Application {action}ed.")
            
            # HTMX response or full redirect
            if request.headers.get('HX-Request'):
                return render(request, 'admissions/partials/application_header.html', {
                    'application': application
                })
            return redirect('admissions:application_detail', application_id=application.id)
            
        except Exception as e:
            logger.error(f"Application action error: {str(e)}")
            messages.error(request, "Error processing application.")
            if request.headers.get('HX-Request'):
                return HttpResponse("❌ Error processing request", status=400)
    
    context = {
        'application': application,
        'similar_applications': Application.objects.filter(
            form__school=school,
            applied_class=application.applied_class
        ).exclude(id=application.id)[:5]  # NEW: Show similar applications
    }
    
    # Return partial for HTMX requests
    if request.headers.get('HX-Request'):
        template = 'admissions/partials/application_detail_content.html'
    else:
        template = 'admissions/application_detail.html'
    
    return render(request, template, context)


def create_application_from_submission(form_slug, application_data, parent_user=None):
    """
    Create an Application instance from form submission data.
    
    Args:
        form_slug: ApplicationForm slug
        application_data: Dict with parent/student data
        parent_user: User object for parent (if exists)
    
    Returns:
        Application: Created application instance
    """
    try:
        # Get the form
        application_form = ApplicationForm.objects.get(slug=form_slug, status='active')
        
        # Check if parent exists
        parent_email = application_data['parent_data']['email']
        
        # Get or create parent
        parent, created = Parent.objects.get_or_create(
            user__email=parent_email,
            defaults={
                'user': parent_user or User.objects.get(email=parent_email),
                'phone': application_data['parent_data'].get('phone'),
                'address': application_data['parent_data'].get('address', ''),
            }
        )
        
        # Get applied class if specified
        applied_class = None
        if application_data['student_data'].get('class_group_id'):
            try:
                applied_class = ClassGroup.objects.get(
                    id=application_data['student_data']['class_group_id'],
                    school=application_form.school
                )
            except ClassGroup.DoesNotExist:
                pass
        
        # Create the application
        application = Application.objects.create(
            form=application_form,
            parent=parent,
            data=application_data,
            priority='normal',
            applied_class=applied_class,
            previous_school_info={
                'school': application_data['student_data'].get('previous_school', ''),
                'class': application_data['student_data'].get('previous_class', ''),
            }
        )
        
        # Update form counter
        application_form.applications_so_far += 1
        application_form.save(update_fields=['applications_so_far'])
        
        logger.info(f"Application created - ID: {application.id}, Number: {application.application_number}")
        return application
        
    except Exception as e:
        logger.error(f"Failed to create application - Form: {form_slug}, Error: {str(e)}")
        raise

    
    
def public_application_start_view(request, form_slug):
    """
    Landing page with form information.
    Shows eligibility, requirements, and a clear "Start Application" button.
    """
    logger.info(f"Application landing page - Slug: {form_slug}")
    
    try:
        form = get_object_or_404(ApplicationForm, slug=form_slug, status='active')
        
        if not form.is_open:
            logger.warning(f"Form {form_slug} is closed")
            return render(request, 'admissions/application_closed.html', {'form': form})
        
        available_classes = ClassGroup.objects.filter(
            school=form.school,
            education_level__in=form.available_classes
        ).select_related('education_level')
        
        context = {
            'form': form,
            'available_classes': available_classes,
            'today': timezone.now().date(),
        }
        
        return render(request, 'admissions/public_application_start.html', context)
        
    except Exception as e:
        logger.error(f"Error loading landing page: {str(e)}")
        return render(request, 'admissions/application_error.html', status=500)


def public_application_form_view(request, form_slug):
    """
    Full-page application form.
    Requires authentication.
    """
    logger.info(f"Application form page - Slug: {form_slug}, User: {request.user.id}")
    
    # Authentication check
    if not request.user.is_authenticated:
        messages.info(request, "Please log in to start your application.")
        return redirect(f"{reverse('account_login')}?next={request.path}")
    
    try:
        form = get_object_or_404(ApplicationForm, slug=form_slug, status='active')
        
        logger.info(f"Form found - ID: {form.id}, Name: {form.name}")
        logger.info(f"Form available_classes data: {form.available_classes}")
        logger.info(f"Form available_classes type: {type(form.available_classes)}")
        
        if not form.is_open:
            messages.warning(request, "This application form is no longer accepting submissions.")
            return redirect('admissions:public_application_start', form_slug=form_slug)
        
        # Check if user already has a pending application
        existing_app = None
        if hasattr(request.user, 'parent'):
            existing_app = Application.objects.filter(
                form=form,
                parent=request.user.parent,
                status__in=['submitted', 'under_review', 'staff_review']
            ).first()
        
        if existing_app:
            messages.info(request, f"You already have a pending application: {existing_app.application_number}")
            return redirect('users:my_applications')
        
        # DEBUG: Log all classes in the school
        all_school_classes = ClassGroup.objects.filter(school=form.school)
        logger.info(f"Total classes in school: {all_school_classes.count()}")
        for cls in all_school_classes:
            logger.info(f"Class: {cls.id} - {cls.name} - Education Level: {cls.education_level.id if cls.education_level else 'None'}")
        
        # Get available classes for this form
        if form.available_classes:
            logger.info(f"Filtering classes by education_level IDs: {form.available_classes}")
            available_classes = ClassGroup.objects.filter(
                school=form.school,
                education_level_id__in=form.available_classes  # Changed from education_level__in
            ).select_related('education_level')
        else:
            # If no specific education levels set, show all classes
            logger.info("No specific education levels set, showing all classes")
            available_classes = ClassGroup.objects.filter(
                school=form.school
            ).select_related('education_level')
        
        logger.info(f"Available classes found: {available_classes.count()}")
        for cls in available_classes:
            logger.info(f"Available Class: {cls.name} - Level: {cls.education_level.name if cls.education_level else 'N/A'}")
        
        context = {
            'form': form,
            'available_classes': available_classes,
            'today': timezone.now().date(),
        }
        
        return render(request, 'admissions/public_application_form.html', context)
        
    except Http404:
        messages.error(request, "Application form not found.")
        return redirect('school_discovery')
    except Exception as e:
        logger.error(f"Error loading form: {str(e)}", exc_info=True)
        messages.error(request, "Error loading application form.")
        return redirect('admissions:public_application_start', form_slug=form_slug)



def public_application_submit_view(request, form_slug):
    """Handle public application submission."""
    logger.info(f"Application submission started - Slug: {form_slug}, User: {request.user}")
    
    # Authentication check
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required. Please log in.',
            'redirect_url': f"{reverse('account_login')}?next={request.path}"
        }, status=401)
    
    try:
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Invalid request method'
            }, status=400)
        
        # Parse application data from form
        application_data = {
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
                'class_group_id': request.POST.get('class_group'),
            },
        }
        
        # Handle file uploads
        documents = []
        for i in range(1, 6):  # Support up to 5 documents
            file_key = f'document_{i}'
            if file_key in request.FILES:
                document_data = ApplicationService._handle_document_upload(
                    request.FILES[file_key],
                    form_slug,
                    request.user
                )
                if document_data:
                    documents.append(document_data)
        
        if documents:
            application_data['documents'] = documents
        
        # Additional notes
        if request.POST.get('additional_notes'):
            application_data['additional_notes'] = request.POST.get('additional_notes').strip()
        
        # Submit application using the new service
        application = ApplicationService.submit_application(
            application_data=application_data,
            form_slug=form_slug,
            user=request.user,
            request=request
        )
        
        logger.info(f"Application submitted successfully: {application.application_number}")
        
        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Application submitted successfully!',
            'application_id': application.id,
            'application_number': application.application_number,
            'redirect_url': reverse('admissions:application_success', args=[application.public_uuid]),
            'is_staff_child': application.is_staff_child,
            'fee_required': bool(application.application_fee_invoice),
            'fee_amount': str(application.application_fee_invoice.amount) if application.application_fee_invoice else '0',
            'scholarship_eligible': application.scholarship_eligible,
        })
        
    except ValidationError as e:
        logger.warning(f"Application validation failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'errors': [str(e)]  # For form field highlighting
        }, status=400)
        
    except Exception as e:
        logger.error(f"Application submission error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred. Please try again or contact support.'
        }, status=500)

@staticmethod
def _handle_document_upload(uploaded_file, form_slug, user):
    """Handle document upload and return metadata."""
    try:
        # Generate unique filename
        import os
        from django.conf import settings
        
        ext = os.path.splitext(uploaded_file.name)[1]
        filename = f"{form_slug}_{user.id}_{uuid.uuid4().hex[:8]}{ext}"
        
        # Save file (you'll need to implement your storage logic)
        file_path = os.path.join('application_documents', filename)
        
        # Save to storage (example using default storage)
        from django.core.files.storage import default_storage
        saved_path = default_storage.save(file_path, uploaded_file)
        
        return {
            'name': uploaded_file.name,
            'stored_name': filename,
            'path': saved_path,
            'size': uploaded_file.size,
            'type': uploaded_file.content_type,
            'uploaded_at': timezone.now().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Document upload failed: {str(e)}")
        return None
        
        
