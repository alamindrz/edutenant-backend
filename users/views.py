# users/views.py
"""
CLEANED USER VIEWS - Using shared architecture
NO circular imports, PROPER service usage, WELL LOGGED
"""
import logging
from typing import Optional
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from typing import Any

from django.contrib.auth import get_user_model


# SHARED IMPORTS
from shared.decorators.permissions import require_role, require_school_context
from shared.constants import PARENT_PHONE_FIELD, StatusChoices
from shared.utils.field_mapping import FieldMapper


# others
from django.db.models import Count
from django.utils import timezone
from datetime import date
from django.apps import apps
from django.contrib import messages




# LOCAL SERVICES
from .services import (
    SchoolOnboardingService,
    StaffService,
    EmailService,
    ValidationService,
    ValidationError,
    SchoolOnboardingError,
)

# LOCAL FORMS
from .forms import (
    SchoolOnboardingForm,
    TeacherApplicationForm,
    StaffCreationForm,
    RoleCreationForm,
)

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'users'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def recover_school_context(request) -> Optional[Any]:
    """Recover school context when middleware fails."""
    if hasattr(request, 'user') and request.user.is_authenticated:
        # Method 1: User's current_school
        if hasattr(request.user, 'current_school') and request.user.current_school:
            return request.user.current_school

        # Method 2: First profile school
        try:
            Profile = _get_model('Profile')
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                # Update user's current_school for consistency
                request.user.current_school = profile.school
                request.user.save()
                return profile.school
        except Exception as e:
            logger.error(f"School recovery failed: {e}", exc_info=True)

    return None


# ============ PUBLIC VIEWS ============


def school_onboarding_start(request):
    """
    School onboarding process that handles both user registration and school creation.
    """
    # If user is already logged in and has a school, redirect to dashboard
    if request.user.is_authenticated:
        if hasattr(request, 'school') and request.school:
            messages.info(request, f"You already have a school: {request.school.name}")
            return redirect('users:dashboard')
    
    if request.method == 'POST':
        logger.info("School onboarding POST request received")
        
        # Use your existing form
        form = SchoolOnboardingForm(request.POST)
        
        if not form.is_valid():
            logger.warning(f"Form validation failed: {form.errors}")
            # Show form errors to user
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, error)
                    else:
                        # Get field label for better error message
                        field_label = form.fields[field].label or field.replace('_', ' ').title()
                        messages.error(request, f"{field_label}: {error}")
            return render(request, 'users/school_onboarding.html', {'form': form})

        try:
            logger.info("Form is valid, processing school creation...")
            
            cleaned_data = form.cleaned_data
            
            # Check if user already exists (by email)
            User = get_user_model()
            admin_email = cleaned_data['admin_email']
            
            if User.objects.filter(email=admin_email).exists():
                # User exists, check if they're logged in
                existing_user = User.objects.get(email=admin_email)
                
                if request.user.is_authenticated:
                    if request.user != existing_user:
                        messages.error(request, 
                            f"This email is already registered to another account. "
                            f"Please sign in with the correct account or use a different email."
                        )
                        return render(request, 'users/school_onboarding.html', {'form': form})
                    # User is logged in and this is their email - proceed
                    admin_user = request.user
                else:
                    # User exists but isn't logged in
                    messages.error(request,
                        f"An account with email '{admin_email}' already exists. "
                        f"Please sign in first, or use a different email address."
                    )
                    return redirect('account_login')
            else:
                # Create new user if not logged in
                if not request.user.is_authenticated:
                    # Create user from form data
                    admin_user = User.objects.create_user(
                        username=admin_email,
                        email=admin_email,
                        password=cleaned_data['admin_password'],
                        first_name=cleaned_data.get('admin_first_name', ''),
                        last_name=cleaned_data.get('admin_last_name', '')
                    )
                    
                    # Add phone if provided
                    if 'admin_phone' in cleaned_data and cleaned_data['admin_phone']:
                        admin_user.phone = cleaned_data['admin_phone']
                        admin_user.save()
                    
                    # Log in the new user
                    admin_user.backend = 'django.contrib.auth.backends.ModelBackend'
                    login(request, admin_user)
                    logger.info(f"New user created and logged in: {admin_email}")
                else:
                    # User is already logged in
                    admin_user = request.user
            
            # Now create the school using your existing service
            logger.info(f"Creating school for user: {admin_user.email}")
            
            # Prepare data for your SchoolOnboardingService
            school_data = {
                'school_name': cleaned_data['school_name'],
                'school_type': cleaned_data['school_type'],
                'contact_email': cleaned_data.get('contact_email', admin_email),
                'phone_number': cleaned_data.get('phone_number'),
                'address': cleaned_data.get('address'),
                'subdomain': cleaned_data.get('subdomain'),
                'bank_code': cleaned_data.get('bank_code'),
                'account_number': cleaned_data.get('account_number'),
                'account_name': cleaned_data.get('account_name'),
                'admin_email': admin_email,
                'admin_first_name': admin_user.first_name,
                'admin_last_name': admin_user.last_name,
                'admin_phone': getattr(admin_user, 'phone', ''),
            }
            
            # Use your existing service to create school
            school = SchoolOnboardingService.create_school_from_template(school_data)
            logger.info(f"School created successfully: {school.name}")
            
            # Create profile for user in this school
            try:
                from .models import Profile, Role
                
                # Get or create default admin role
                default_role, _ = Role.objects.get_or_create(
                    system_role_type='principal',
                    defaults={
                        'name': 'School Principal',
                        'can_manage_staff': True,
                        'can_manage_students': True,
                        'can_manage_academics': True,
                        'can_manage_finances': True,
                        'can_manage_roles': True,
                        'can_view_reports': True,
                        'can_communicate': True,
                        'can_manage_attendance': True,
                        'can_manage_admissions': True,
                    }
                )
                
                # Create profile
                Profile.objects.create(
                    user=admin_user,
                    school=school,
                    role=default_role
                )
                logger.info(f"Profile created for {admin_user.email} in school {school.name}")
                
            except Exception as profile_error:
                logger.error(f"Error creating profile: {profile_error}")
                # Continue anyway - school was created successfully
            
            # Set session school
            request.session['current_school_id'] = school.id
            
            # Send success message
            messages.success(
                request,
                f"Congratulations! Your school '{school.name}' has been created successfully. "
                f"You're now logged in as the school principal."
            )
            
            # Redirect to dashboard
            return redirect('users:dashboard')

        except SchoolOnboardingError as e:
            logger.error(f"School onboarding error: {e}", exc_info=True)
            messages.error(request, str(e))
            
            # If user was created but school failed, log them out
            if 'admin_user' in locals() and not request.user.is_authenticated:
                logout(request)
                
        except Exception as e:
            logger.error(f"Unexpected error during onboarding: {e}", exc_info=True)
            messages.error(
                request,
                "An unexpected error occurred during setup. Please try again or contact support."
            )
            
            # Clean up: logout if user was just created
            if 'admin_user' in locals() and not request.user.is_authenticated:
                logout(request)
    
    else:
        # GET request - initialize form
        form = SchoolOnboardingForm()
        
        # Pre-fill with user data if logged in
        if request.user.is_authenticated:
            initial_data = {
                'admin_email': request.user.email,
                'admin_first_name': request.user.first_name,
                'admin_last_name': request.user.last_name,
            }
            
            # Add phone if exists on user model
            if hasattr(request.user, 'phone') and request.user.phone:
                initial_data['admin_phone'] = request.user.phone
            
            form = SchoolOnboardingForm(initial=initial_data)

    context = {
        'form': form,
        'page_title': 'Create Your School',
        'page_subtitle': 'Everything you need to start managing your school digitally',
        'user_is_authenticated': request.user.is_authenticated,
    }
    
    return render(request, 'users/school_onboarding.html', context)




def check_subdomain_availability(request):
    """API endpoint to check subdomain availability."""
    subdomain = request.GET.get('subdomain', '').strip().lower()
    
    if not subdomain:
        return JsonResponse({'error': 'Subdomain required'}, status=400)
    
    # Validate format
    import re
    if not re.match(r'^[a-zA-Z0-9-]+$', subdomain):
        return JsonResponse({'available': False, 'error': 'Invalid format'})
    
    if len(subdomain) < 3:
        return JsonResponse({'available': False, 'error': 'Too short'})
    
    if len(subdomain) > 30:
        return JsonResponse({'available': False, 'error': 'Too long'})
    
    # Check reserved words
    reserved = ['admin', 'api', 'app', 'dashboard', 'help', 'support', 'www', 'mail', 'ftp']
    if subdomain in reserved:
        return JsonResponse({'available': False, 'error': 'Reserved word'})
    
    # Check database
    from core.models import School
    exists = School.objects.filter(subdomain=subdomain).exists()
    
    suggestions = []
    if exists:
        # Generate suggestions
        for i in range(1, 5):
            suggestion = f"{subdomain}{i}"
            if not School.objects.filter(subdomain=suggestion).exists():
                suggestions.append(suggestion)
                if len(suggestions) >= 3:
                    break
    
    return JsonResponse({
        'available': not exists,
        'suggestions': suggestions
    })


def accept_invitation_view(request, token: str):
    """Accept staff invitation and create account."""
    StaffInvitation = _get_model('StaffInvitation')

    try:
        invitation = StaffInvitation.objects.get(token=token, status='pending')

        if not invitation.is_valid():
            messages.error(request, "This invitation has expired or is no longer valid.")
            return redirect('account_login')

        if request.method == 'POST':
            try:
                # Use FieldMapper to standardize field names
                user_data = FieldMapper.map_form_to_model(request.POST, 'staff_invitation')

                # Validate passwords match
                if request.POST.get('password') != request.POST.get('password_confirm'):
                    messages.error(request, "Passwords do not match.")
                    return render(request, 'users/accept_invitation.html', {
                        'invitation': invitation
                    })

                user = StaffService.accept_invitation(token, user_data)

                # Log the user in
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)

                messages.success(
                    request,
                    f"Welcome to {invitation.school.name}! Your account has been created."
                )
                return redirect('users:dashboard')

            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Error accepting invitation: {str(e)}", exc_info=True)
                messages.error(request, "An error occurred. Please try again.")

        context = {'invitation': invitation}
        return render(request, 'users/accept_invitation.html', context)

    except StaffInvitation.DoesNotExist:
        messages.error(request, "Invalid invitation link.")
        return redirect('account_login')
    except Exception as e:
        logger.error(f"Error loading invitation: {str(e)}", exc_info=True)
        messages.error(request, "Invalid invitation link.")
        return redirect('account_login')



def check_subdomain_availability(request):
    """AJAX endpoint to check subdomain availability."""
    subdomain = request.GET.get('subdomain', '').strip().lower()

    if not subdomain:
        return JsonResponse({'error': 'No subdomain provided'}, status=400)

    try:
        # Check availability
        available = SchoolOnboardingService.is_subdomain_available(subdomain)

        # Get suggestions if not available
        suggestions = []
        if not available:
            suggestions = SchoolOnboardingService.get_subdomain_suggestions(subdomain)

        return JsonResponse({
            'available': available,
            'suggestions': suggestions,
            'subdomain': subdomain
        })

    except Exception as e:
        logger.error(f"Subdomain check error: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)



def validate_school_name(request):
    """HTMX endpoint to validate school name."""
    school_name = request.POST.get('school_name', '').strip()

    if not school_name:
        return JsonResponse({'valid': False, 'error': 'School name is required'})

    School = _get_model('School', 'core')
    if School.objects.filter(name__iexact=school_name).exists():
        return JsonResponse({
            'valid': False,
            'error': 'A school with this name already exists'
        })

    return JsonResponse({'valid': True})


# ============ AUTHENTICATED VIEWS ============
@login_required
@require_school_context()
def dashboard_view(request):
    """
    Main dashboard view for authenticated users with school context.
    Shows basic information and quick links.
    """
    school = request.school

    if not school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')

    # Get user's profile - FIXED: Profile model doesn't have is_active field
    try:
        Profile = apps.get_model('users', 'Profile')
        profile = Profile.objects.select_related('role').get(
            user=request.user,
            school=school,
            # REMOVED: is_active=True - Profile doesn't have this field
        )
        role = profile.role
    except Profile.DoesNotExist:
        messages.warning(request, "You don't have a profile in this school.")
        # If user has other profiles, redirect to school selection
        other_profiles = Profile.objects.filter(user=request.user).exists()
        if other_profiles:
            return redirect('users:school_list')
        else:
            # If no profiles at all, maybe show onboarding
            return redirect('users:profile')

    # Get basic stats
    stats = get_dashboard_stats(school, role, request.user)

    # Get quick links based on role
    quick_links = get_quick_links(role, school)

    # Get recent activities
    recent_activities = get_recent_activities(school)

    context = {
        'school': school,
        'user_role': role,
        'user_profile': profile,
        'stats': stats,
        'quick_links': quick_links,
        'recent_activities': recent_activities,
        'page_title': 'Dashboard',
        'page_subtitle': f'Welcome to {school.name}',
    }

    return render(request, 'dashboard.html', context)


def get_dashboard_stats(school, role, user):
    """
    Get dashboard statistics.
    """
    stats = {}

    # Basic stats for all roles
    try:
        Student = apps.get_model('students', 'Student')
        stats['total_students'] = Student.objects.filter(school=school).count()
    except:
        stats['total_students'] = 0

    try:
        Staff = apps.get_model('users', 'Staff')
        stats['total_staff'] = Staff.objects.filter(school=school).count()
    except:
        stats['total_staff'] = 0

    try:
        Class = apps.get_model('core', 'Class')
        stats['total_classes'] = Class.objects.filter(school=school).count()
    except:
        stats['total_classes'] = 0

    # Pending applications
    try:
        Application = apps.get_model('admissions', 'Application')
        stats['pending_applications'] = Application.objects.filter(
            school=school,
            status='pending'
        ).count()
    except:
        stats['pending_applications'] = 0

    # Unpaid invoices
    try:
        Invoice = apps.get_model('billing', 'Invoice')
        stats['unpaid_invoices'] = Invoice.objects.filter(
            school=school,
            status='unpaid'
        ).count()
    except:
        stats['unpaid_invoices'] = 0

    # Role-specific stats
    if role and hasattr(role, 'system_role_type'):
        role_type = role.system_role_type

        # Teacher stats
        if role_type == 'teacher':
            try:
                # Get teacher's classes
                Staff = apps.get_model('users', 'Staff')
                teacher = Staff.objects.get(user=user, school=school)

                # Check if teacher has assigned_classes relationship
                if hasattr(teacher, 'assigned_classes'):
                    stats['assigned_classes'] = teacher.assigned_classes.count()

                    # Count students in assigned classes
                    student_count = 0
                    for class_obj in teacher.assigned_classes.all():
                        if hasattr(class_obj, 'students'):
                            student_count += class_obj.students.count()
                    stats['assigned_students'] = student_count
                else:
                    # Alternative: Check through SubjectAssignment or similar
                    stats['assigned_classes'] = 0
                    stats['assigned_students'] = 0
            except Staff.DoesNotExist:
                stats['assigned_classes'] = 0
                stats['assigned_students'] = 0

        # Parent stats
        elif role_type == 'parent':
            try:
                Parent = apps.get_model('students', 'Parent')
                parent = Parent.objects.get(user=user, school=school)
                stats['children_count'] = parent.children.count()
            except Parent.DoesNotExist:
                stats['children_count'] = 0

    return stats


def get_quick_links(role, school):
    """
    Get quick action links based on user role.
    """
    quick_links = []

    if not role:
        return quick_links

    # Common links for all authenticated users
    quick_links.append({
        'title': 'My Profile',
        'url': 'users:profile',
        'icon': 'bi-person',
        'description': 'View and update your profile'
    })

    quick_links.append({
        'title': 'Switch School',
        'url': 'users:school_list',
        'icon': 'bi-building',
        'description': 'Change your current school'
    })

    # Admin/Principal links
    if hasattr(role, 'system_role_type') and role.system_role_type in ['principal', 'admin_staff']:
        quick_links.extend([
            {
                'title': 'Manage Staff',
                'url': 'users:staff_list',
                'icon': 'bi-person-badge',
                'description': 'Add and manage staff members'
            },
            {
                'title': 'View Students',
                'url': 'students:student_list',
                'icon': 'bi-people',
                'description': 'Browse student directory'
            },
            {
                'title': 'Admissions',
                'url': 'admissions:dashboard',
                'icon': 'bi-door-open',
                'description': 'Manage applications'
            },
            {
                'title': 'Billing',
                'url': 'billing:dashboard',
                'icon': 'bi-cash-coin',
                'description': 'Manage fees and invoices'
            },
        ])

    # Teacher links
    if hasattr(role, 'system_role_type') and role.system_role_type == 'teacher':
        quick_links.extend([
            {
                'title': 'Take Attendance',
                'url': 'attendance:dashboard',
                'icon': 'bi-check-circle',
                'description': 'Mark student attendance'
            },
            {
                'title': 'My Classes',
                'url': '#',
                'icon': 'bi-journal',
                'description': 'View assigned classes'
            },
        ])

    # Parent links
    if hasattr(role, 'system_role_type') and role.system_role_type == 'parent':
        quick_links.extend([
            {
                'title': 'My Children',
                'url': 'students:parent_children',
                'icon': 'bi-people',
                'description': 'View your children'
            },
            {
                'title': 'Invoices',
                'url': 'billing:parent_invoices',
                'icon': 'bi-receipt',
                'description': 'View and pay invoices'
            },
        ])

    return quick_links[:6]  # Limit to 6 links


def get_recent_activities(school):
    """
    Get recent activities for the school.
    """
    activities = []

    # Recent students
    try:
        Student = apps.get_model('students', 'Student')
        recent_students = Student.objects.filter(
            school=school
        ).order_by('-created_at')[:3]

        for student in recent_students:
            activities.append({
                'type': 'student',
                'title': 'New student enrolled',
                'description': student.get_full_name() if hasattr(student, 'get_full_name') else student.name,
                'time': student.created_at if hasattr(student, 'created_at') else timezone.now(),
                'icon': 'bi-person-plus',
                'color': 'primary'
            })
    except:
        pass

    # Recent invoices
    try:
        Invoice = apps.get_model('billing', 'Invoice')
        recent_invoices = Invoice.objects.filter(
            school=school
        ).order_by('-created_at')[:3]

        for invoice in recent_invoices:
            activities.append({
                'type': 'invoice',
                'title': 'Invoice created',
                'description': f'#{invoice.invoice_number}' if hasattr(invoice, 'invoice_number') else 'New invoice',
                'time': invoice.created_at if hasattr(invoice, 'created_at') else timezone.now(),
                'icon': 'bi-receipt',
                'color': 'success'
            })
    except:
        pass

    # Sort by time
    activities.sort(key=lambda x: x['time'], reverse=True)

    return activities[:5]

@login_required
def profile_view(request):
    """User profile management view."""
    Profile = _get_model('Profile')
    user_profiles = Profile.objects.filter(
        user=request.user
    ).select_related('school', 'role')

    context = {'user_profiles': user_profiles}
    return render(request, 'users/profile.html', context)


@login_required
def school_list_view(request):
    """List schools user has access to."""
    School = _get_model('School', 'core')
    Profile = _get_model('Profile')

    user_schools = School.objects.filter(
        profile__user=request.user,
        is_active=True
    ).distinct()

    # Calculate statistics
    active_schools_count = user_schools.count()
    admin_schools_count = user_schools.filter(
        profile__user=request.user,
        profile__role__system_role_type='principal'
    ).distinct().count()

    teacher_schools_count = user_schools.filter(
        profile__user=request.user,
        profile__role__system_role_type='teacher'
    ).distinct().count()

    context = {
        'schools': user_schools,
        'active_schools_count': active_schools_count,
        'admin_schools_count': admin_schools_count,
        'teacher_schools_count': teacher_schools_count,
    }
    return render(request, 'users/school_list.html', context)


@login_required
def switch_school_view(request, school_id: int):
    """Switch current school context for user."""
    School = _get_model('School', 'core')
    Profile = _get_model('Profile')

    school = get_object_or_404(School, id=school_id, is_active=True)

    # Check if user has access to this school
    if not Profile.objects.filter(user=request.user, school=school).exists():
        messages.error(request, "You don't have access to this school.")
        return redirect('users:school_list')

    request.user.current_school = school
    request.user.save()

    messages.success(request, f"Switched to {school.name}")
    return redirect('users:dashboard')




@login_required
@require_school_context()
def dashboard_stats_partial(request):
    """
    HTMX partial for dashboard stats.
    """
    school = request.school

    # Calculate basic stats
    stats = {
        'student_count': 0,
        'staff_count': 0,
        'class_count': 0,
        'pending_applications': 0,
        'unpaid_invoices': 0,
    }

    # Student count
    try:
        Student = apps.get_model('students', 'Student')
        stats['student_count'] = Student.objects.filter(school=school, is_active=True).count()
    except:
        pass

    # Staff count
    try:
        Staff = apps.get_model('users', 'Staff')
        stats['staff_count'] = Staff.objects.filter(school=school, is_active=True).count()
    except:
        pass

    # Class count
    try:
        Class = apps.get_model('core', 'Class')
        stats['class_count'] = Class.objects.filter(school=school, is_active=True).count()
    except:
        pass

    # Pending applications
    try:
        Application = apps.get_model('admissions', 'Application')
        stats['pending_applications'] = Application.objects.filter(
            school=school,
            status='pending'
        ).count()
    except:
        pass

    # Unpaid invoices
    try:
        Invoice = apps.get_model('billing', 'Invoice')
        stats['unpaid_invoices'] = Invoice.objects.filter(
            school=school,
            status='unpaid'
        ).count()
    except:
        pass

    context = {
        'stats': stats,
        'school': school,
    }

    return render(request, 'partials/dashboard_stats.html', context)


@login_required
@require_school_context()
def recent_activity_partial(request):
    """
    HTMX partial for recent activity feed.
    """
    school = request.school
    activities = []

    # Recent students
    try:
        Student = apps.get_model('students', 'Student')
        recent_students = Student.objects.filter(
            school=school,
            is_active=True
        ).order_by('-created_at')[:3]

        for student in recent_students:
            activities.append({
                'type': 'student',
                'title': 'New student enrolled',
                'description': student.get_full_name() if hasattr(student, 'get_full_name') else student.name,
                'time': student.created_at,
                'icon': 'bi-person-plus',
                'color': 'primary'
            })
    except:
        pass

    # Recent invoices
    try:
        Invoice = apps.get_model('billing', 'Invoice')
        recent_invoices = Invoice.objects.filter(
            school=school
        ).order_by('-created_at')[:3]

        for invoice in recent_invoices:
            activities.append({
                'type': 'invoice',
                'title': 'Invoice created',
                'description': f'#{invoice.invoice_number}' if hasattr(invoice, 'invoice_number') else 'New invoice',
                'time': invoice.created_at,
                'icon': 'bi-receipt',
                'color': 'success'
            })
    except:
        pass

    # Sort by time
    activities.sort(key=lambda x: x['time'], reverse=True)

    context = {
        'activities': activities[:5],
        'school': school,
    }

    return render(request, 'partials/recent_activity.html', context)

# ============ STAFF MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_staff')
def staff_list_view(request):
    """List all staff members for the current school."""
    school = request.school

    Staff = _get_model('Staff')
    StaffInvitation = _get_model('StaffInvitation')

    # Get staff statistics
    total_staff = Staff.objects.filter(school=school).count()
    active_staff = Staff.objects.filter(school=school, is_active=True).count()
    teaching_staff = Staff.objects.filter(
        school=school,
        is_teaching_staff=True,
        is_active=True
    ).count()

    # Get applications count
    pending_applications_count = StaffService.get_pending_applications(school).count()

    # Get invitations count
    pending_invitations_count = StaffInvitation.objects.filter(
        school=school, status='pending'
    ).count()

    # Get unique departments
    departments = Staff.objects.filter(
        school=school,
        department__isnull=False
    ).exclude(department='').values_list('department', flat=True).distinct()

    context = {
        'total_staff': total_staff,
        'active_staff': active_staff,
        'teaching_staff': teaching_staff,
        'pending_applications_count': pending_applications_count,
        'pending_invitations_count': pending_invitations_count,
        'departments': departments,
    }
    return render(request, 'users/staff_list.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def staff_create_view(request):
    """Create new staff member."""
    school = request.school

    if request.method == 'POST':
        form = StaffCreationForm(request.POST, school=school)
        if form.is_valid():
            try:
                staff = form.save(commit=False)
                staff.school = school
                staff.save()

                # Create user account if requested
                if form.cleaned_data.get('create_user_account'):
                    staff.create_user_account()

                messages.success(
                    request,
                    f"Staff member {staff.full_name} created successfully!"
                )
                return redirect('users:staff_list')
            except Exception as e:
                logger.error(f"Error creating staff member: {str(e)}")
                messages.error(request, f"Error creating staff member: {str(e)}")
    else:
        form = StaffCreationForm(school=school)

    context = {
        'form': form,
        'page_title': 'Add New Staff Member'
    }
    return render(request, 'users/staff_form.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def staff_detail_view(request, staff_id: int):
    """View staff member details."""
    school = request.school
    Staff = _get_model('Staff')
    StaffAssignment = _get_model('StaffAssignment')
    Role = _get_model('Role')

    staff = get_object_or_404(Staff, id=staff_id, school=school)
    assignments = StaffAssignment.objects.filter(staff=staff, is_active=True)
    available_roles = Role.objects.filter(
        school=school,
        is_active=True
    ).exclude(id__in=assignments.values_list('role_id', flat=True))

    context = {
        'staff': staff,
        'assignments': assignments,
        'available_roles': available_roles,
    }
    return render(request, 'users/staff_detail.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def assign_role_view(request, staff_id: int):
    """Assign role to staff member."""
    school = request.school
    Staff = _get_model('Staff')
    StaffAssignment = _get_model('StaffAssignment')
    Role = _get_model('Role')
    Profile = _get_model('Profile')

    staff = get_object_or_404(Staff, id=staff_id, school=school)

    if request.method == 'POST':
        role_id = request.POST.get('role_id')
        role = get_object_or_404(Role, id=role_id, school=school)

        # Check if assignment already exists
        existing_assignment = StaffAssignment.objects.filter(
            staff=staff,
            role=role
        ).first()

        if existing_assignment:
            if existing_assignment.is_active:
                messages.warning(
                    request,
                    f"{staff.full_name} already has the {role.name} role."
                )
            else:
                existing_assignment.is_active = True
                existing_assignment.assigned_by = request.user
                existing_assignment.save()
                messages.success(
                    request,
                    f"{role.name} role reassigned to {staff.full_name}."
                )
        else:
            StaffAssignment.objects.create(
                staff=staff,
                role=role,
                assigned_by=request.user
            )
            messages.success(
                request,
                f"{role.name} role assigned to {staff.full_name}."
            )

        # If staff has a user account, update their profile
        if staff.user:
            profile, created = Profile.objects.get_or_create(
                user=staff.user,
                school=school,
                defaults={'role': role}
            )
            if not created:
                profile.role = role
                profile.save()

    return redirect('users:staff_detail', staff_id=staff_id)


@login_required
@require_school_context
@require_role('manage_staff')
def remove_role_assignment(request, staff_id: int, assignment_id: int):
    """Remove role assignment from staff member."""
    school = request.school
    Staff = _get_model('Staff')
    StaffAssignment = _get_model('StaffAssignment')

    staff = get_object_or_404(Staff, id=staff_id, school=school)
    assignment = get_object_or_404(
        StaffAssignment,
        id=assignment_id,
        staff=staff
    )

    assignment.is_active = False
    assignment.save()

    messages.success(
        request,
        f"{assignment.role.name} role removed from {staff.full_name}."
    )
    return redirect('users:staff_detail', staff_id=staff_id)


# ============ ROLE MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_roles')
def role_create_view(request):
    """Create new custom role."""
    school = request.school

    if request.method == 'POST':
        form = RoleCreationForm(request.POST, school=school)
        if form.is_valid():
            try:
                role = form.save()
                messages.success(request, f"Role '{role.name}' created successfully!")
                return redirect('users:role_list')
            except Exception as e:
                logger.error(f"Error creating role: {str(e)}")
                messages.error(request, f"Error creating role: {str(e)}")
    else:
        form = RoleCreationForm(school=school)

    context = {
        'form': form,
        'page_title': 'Create New Role'
    }
    return render(request, 'users/role_form.html', context)


@login_required
@require_school_context
@require_role('manage_roles')
def role_list_view(request):
    """List all roles for the current school."""
    school = request.school
    Role = _get_model('Role')

    roles = Role.objects.filter(school=school).prefetch_related('staffassignment_set')

    # Filter by category if provided
    category_filter = request.GET.get('category', '')
    if category_filter:
        roles = roles.filter(category=category_filter)

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        roles = roles.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Get role statistics
    role_stats = {}
    for role in roles:
        role_stats[role.id] = {
            'total_assignments': role.staffassignment_set.filter(is_active=True).count(),
            'is_system_role': role.is_system_role,
        }

    context = {
        'roles': roles,
        'role_stats': role_stats,
        'search_query': search_query,
        'category_filter': category_filter,
        'role_categories': Role.ROLE_CATEGORIES,
    }
    return render(request, 'users/role_list.html', context)


@login_required
@require_school_context
@require_role('manage_roles')
def role_create_view(request):
    """Create new custom role."""
    school = request.school

    if request.method == 'POST':
        form = RoleCreationForm(request.POST, school=school)
        if form.is_valid():
            try:
                role = form.save()
                messages.success(request, f"Role '{role.name}' created successfully!")
                return redirect('users:role_list')
            except Exception as e:
                logger.error(f"Error creating role: {str(e)}")
                messages.error(request, f"Error creating role: {str(e)}")
    else:
        form = RoleCreationForm(school=school)

    context = {
        'form': form,
        'page_title': 'Create New Role'
    }
    return render(request, 'users/role_form.html', context)


@login_required
@require_school_context
@require_role('manage_roles')
def role_edit_view(request, role_id: int):
    """Edit existing role."""
    school = request.school
    Role = _get_model('Role')

    role = get_object_or_404(Role, id=role_id, school=school)

    # Prevent editing system roles
    if role.is_system_role:
        messages.error(request, "System roles cannot be edited.")
        return redirect('users:role_list')

    if request.method == 'POST':
        form = RoleCreationForm(request.POST, instance=role, school=school)
        if form.is_valid():
            try:
                role = form.save()
                messages.success(request, f"Role '{role.name}' updated successfully!")
                return redirect('users:role_list')
            except Exception as e:
                logger.error(f"Error updating role: {str(e)}")
                messages.error(request, f"Error updating role: {str(e)}")
    else:
        # Initialize form with current permissions
        initial_data = {
            'can_manage_roles': 'manage_roles' in role.permissions,
            'can_manage_staff': 'manage_staff' in role.permissions,
            'can_manage_students': 'manage_students' in role.permissions,
            'can_manage_academics': 'manage_academics' in role.permissions,
            'can_manage_finances': 'manage_finances' in role.permissions,
            'can_view_reports': 'view_reports' in role.permissions,
            'can_communicate': 'communicate' in role.permissions,
        }
        form = RoleCreationForm(
            instance=role,
            initial=initial_data,
            school=school
        )

    context = {
        'form': form,
        'role': role,
        'page_title': f'Edit Role: {role.name}'
    }
    return render(request, 'users/role_form.html', context)


@login_required
@require_school_context
@require_role('manage_roles')
def role_detail_view(request, role_id: int):
    """View role details and assignments."""
    school = request.school
    Role = _get_model('Role')
    StaffAssignment = _get_model('StaffAssignment')

    role = get_object_or_404(Role, id=role_id, school=school)
    assignments = StaffAssignment.objects.filter(
        role=role,
        is_active=True
    ).select_related('staff')

    context = {
        'role': role,
        'assignments': assignments,
        'permissions_display': role.get_permissions_display(),
    }
    return render(request, 'users/role_detail.html', context)


# ============ STAFF INVITATION VIEWS ============

@login_required
@require_school_context
@require_role('manage_staff')
def staff_invite_view(request):
    """Invite teachers/staff to join the school."""
    school = request.school
    Role = _get_model('Role')

    if request.method == 'POST':
        email = request.POST.get('email')
        role_id = request.POST.get('role')
        message = request.POST.get('message', '')

        try:
            invitation = StaffService.invite_teacher(
                school=school,
                invited_by=request.user,
                email=email,
                role_id=role_id,
                message=message
            )

            messages.success(request, f"Invitation sent to {email}")

            if request.headers.get('HX-Request'):
                # Return updated invitations list for HTMX
                pending_invitations = StaffService.get_pending_invitations(school)
                return render(request, 'users/partials/invitations_list.html', {
                    'pending_invitations': pending_invitations
                })
            else:
                return redirect('users:staff_list')

        except ValidationError as e:
            messages.error(request, str(e))
            if request.headers.get('HX-Request'):
                return render(request, 'users/partials/invite_form.html', {
                    'available_roles': Role.objects.filter(school=school, is_active=True),
                    'error': str(e)
                })

    available_roles = Role.objects.filter(school=school, is_active=True)

    context = {
        'available_roles': available_roles,
        'pending_invitations': StaffService.get_pending_invitations(school),
    }

    return render(request, 'users/staff_invite.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def cancel_invitation_view(request, invitation_id: int):
    """Cancel a pending invitation."""
    school = request.school
    StaffInvitation = _get_model('StaffInvitation')

    invitation = get_object_or_404(
        StaffInvitation,
        id=invitation_id,
        school=school,
        status='pending'
    )

    invitation.status = 'expired'
    invitation.save()

    messages.success(request, f"Invitation to {invitation.email} has been cancelled.")

    if request.headers.get('HX-Request'):
        pending_invitations = StaffService.get_pending_invitations(school)
        return render(request, 'users/partials/invitations_list.html', {
            'pending_invitations': pending_invitations
        })
    else:
        return redirect('users:staff_invite')


# ============ TEACHER APPLICATION VIEWS ============

@login_required
@require_school_context
@require_role('manage_staff')
def school_applications_view(request):
    """View for school admins to manage teacher applications."""
    school = request.school
    applications = StaffService.get_pending_applications(school)

    status_filter = request.GET.get('status', 'pending')
    if status_filter:
        applications = applications.filter(status=status_filter)

    context = {
        'applications': applications,
        'status_filter': status_filter,
        'page_title': 'Teacher Applications'
    }
    return render(request, 'users/school_applications.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def approve_application_view(request, application_id: int):
    """Approve a teacher application."""
    school = request.school
    TeacherApplication = _get_model('TeacherApplication')

    application = get_object_or_404(
        TeacherApplication,
        id=application_id,
        school=school
    )

    try:
        staff = StaffService.approve_application(application, approved_by=request.user)
        messages.success(
            request,
            f"Application approved! Staff account created for {staff.full_name}"
        )

        # Return HTMX response if needed
        if request.headers.get('HX-Request'):
            applications = StaffService.get_pending_applications(school)
            return render(request, 'users/partials/applications_table.html', {
                'applications': applications
            })

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Failed to approve application {application_id}: {str(e)}", exc_info=True)
        messages.error(request, f"Failed to approve application: {str(e)}")

        # If it's a role-related error, suggest running the fix command
        if "Role matching query does not exist" in str(e):
            messages.info(
                request,
                "System roles missing. Please contact administrator to run role setup."
            )

    return redirect('users:school_applications')


@login_required
@require_school_context
@require_role('manage_staff')
def reject_application_view(request, application_id: int):
    """Reject a teacher application."""
    school = request.school
    TeacherApplication = _get_model('TeacherApplication')

    application = get_object_or_404(
        TeacherApplication,
        id=application_id,
        school=school
    )

    reason = request.POST.get('reason', '')
    application.reject(rejected_by=request.user, reason=reason)

    messages.success(
        request,
        f"Application from {application.full_name} has been rejected."
    )
    return redirect('users:school_applications')


@login_required
def my_applications_view(request):
    """Display user's applications."""
    TeacherApplication = _get_model('TeacherApplication')
    applications = TeacherApplication.objects.filter(
        applicant=request.user
    ).order_by('-created_at')

    # Group by school for better organization
    applications_by_school = {}
    for app in applications:
        school_id = app.school.id
        if school_id not in applications_by_school:
            applications_by_school[school_id] = {
                'school': app.school,
                'applications': []
            }
        applications_by_school[school_id]['applications'].append(app)

    context = {
        'applications_by_school': applications_by_school,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(
            status__in=['pending', 'under_review']
        ).count(),
    }

    return render(request, 'users/my_applications.html', context)


# ============ SCHOOL DISCOVERY & APPLICATION ============

@login_required
def school_discovery_view(request):
    """View for teachers to discover and search schools."""
    School = _get_model('School', 'core')
    Profile = _get_model('Profile')

    query = request.GET.get('q', '')
    school_type = request.GET.get('school_type', '')

    # Get schools with open positions
    schools = StaffService.search_schools_for_application(query)

    if school_type:
        schools = schools.filter(school_type=school_type)

    # Check which schools the user already has access to
    user_accessible_schools = set()
    if request.user.is_authenticated:
        user_accessible_schools = set(
            Profile.objects.filter(user=request.user).values_list('school_id', flat=True)
        )

    # Paginate
    paginator = Paginator(schools, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'schools': page_obj,
        'search_query': query,
        'page_title': 'Discover Schools',
        'user_accessible_schools': user_accessible_schools,
    }

    # Return partial for HTMX requests
    if request.headers.get('HX-Request'):
        return render(request, 'users/partials/school_cards.html', context)

    return render(request, 'users/school_discovery.html', context)


@login_required
def apply_to_school_view(request, school_id: int):
    """View for teachers to apply to a specific school."""
    School = _get_model('School', 'core')
    TeacherApplication = _get_model('TeacherApplication')
    OpenPosition = _get_model('OpenPosition')

    school = get_object_or_404(School, id=school_id, is_active=True)

    # Check if user already has a pending application
    existing_application = TeacherApplication.objects.filter(
        school=school,
        email=request.user.email,
        status='pending'
    ).exists()

    if existing_application:
        messages.warning(
            request,
            f"You already have a pending application for {school.name}."
        )
        return redirect('users:school_discovery')

    # Check if school has open positions
    open_positions = OpenPosition.objects.filter(school=school, is_active=True)
    if not open_positions.exists():
        messages.error(request, f"{school.name} is not currently hiring teachers.")
        return redirect('users:school_discovery')

    if request.method == 'POST':
        form = TeacherApplicationForm(request.POST, request.FILES, school=school)
        if form.is_valid():
            try:
                # Use FieldMapper to standardize data
                application_data = FieldMapper.map_form_to_model(
                    form.cleaned_data,
                    'teacher_application'
                )
                application_data['applicant'] = request.user
                application_data['school'] = school

                # Create the application through service (moved from model)
                TeacherApplication.objects.create(**application_data)

                messages.success(
                    request,
                    f"Your application has been submitted to {school.name}! "
                    "The school administration will review your application and contact you."
                )
                return redirect('users:my_applications')

            except Exception as e:
                logger.error(f"Error submitting application: {str(e)}", exc_info=True)
                messages.error(request, f"Error submitting application: {str(e)}")
    else:
        # Pre-fill form with user data
        initial = {
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            PARENT_PHONE_FIELD: request.user.phone_number,  # ✅ Use shared constant
        }
        form = TeacherApplicationForm(school=school, initial=initial)

    context = {
        'school': school,
        'form': form,
        'open_positions': open_positions,
        'page_title': f'Apply to {school.name}'
    }
    return render(request, 'users/apply_to_school.html', context)


# ============ HTMX VIEWS ============

@login_required
@require_school_context
def dashboard_stats_partial(request):
    """HTMX endpoint for dashboard statistics."""
    school = request.school

    stats = {
        'total_staff': Staff.objects.filter(school=school, is_active=True).count(),
        'total_students': Student.objects.filter(school=school, is_active=True).count(),
        'total_parents': Parent.objects.filter(school=school).count(),
        'total_classes': Class.objects.filter(school=school, is_active=True).count(),
        'pending_invitations': StaffInvitation.objects.filter(
            school=school, status='pending'
        ).count(),
    }


@login_required
@require_school_context
def recent_activity_partial(request):
    """HTMX endpoint for recent activity feed."""
    school = request.school

    Staff = _get_model('Staff')
    StaffInvitation = _get_model('StaffInvitation')

    # Get recent staff additions
    recent_staff = Staff.objects.filter(
        school=school
    ).select_related('user').order_by('-id')[:5]

    # Get recent invitations
    recent_invitations = StaffInvitation.objects.filter(
        school=school
    ).select_related('role', 'invited_by').order_by('-created_at')[:5]

    return render(request, 'partials/recent_activity.html', {
        'recent_staff': recent_staff,
        'recent_invitations': recent_invitations,
        'school': school
    })


@login_required
@require_school_context
@require_role('manage_staff')
def staff_table_partial(request):
    """HTMX endpoint for staff table with filters."""
    school = request.school
    Staff = _get_model('Staff')

    staff_members = Staff.objects.filter(school=school).select_related(
        'user'
    ).prefetch_related('staffassignment_set')

    # Apply filters
    active_filter = request.GET.get('active')
    if active_filter is not None:
        staff_members = staff_members.filter(
            is_active=active_filter.lower() == 'true'
        )

    search_query = request.GET.get('search', '')
    if search_query:
        staff_members = staff_members.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(staff_id__icontains=search_query) |
            Q(position__icontains=search_query)
        )

    return render(request, 'users/partials/staff_table.html', {
        'staff_members': staff_members,
        'search_query': search_query,
        'active_filter': active_filter,
    })


@login_required
@require_school_context
@require_role('manage_staff')
def applications_table_partial(request):
    """HTMX endpoint for applications table."""
    school = request.school
    OpenPosition = _get_model('OpenPosition')

    applications = StaffService.get_pending_applications(school)

    status_filter = request.GET.get('status', 'pending')
    if status_filter:
        applications = applications.filter(status=status_filter)

    # Get search and position filters if provided
    search = request.GET.get('search', '')
    position_filter = request.GET.get('position', '')

    # Apply additional filters
    if search:
        applications = applications.filter(
            Q(applicant__first_name__icontains=search) |
            Q(applicant__last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(position_applied__icontains=search)
        )

    if position_filter:
        applications = applications.filter(position_applied=position_filter)

    # Get counts for statistics
    pending_count = applications.filter(status='pending').count()
    approved_count = applications.filter(status=StatusChoices.APPROVED).count()  # ✅ Use shared constant
    rejected_count = applications.filter(status=StatusChoices.REJECTED).count()  # ✅ Use shared constant

    # Get open positions for filter dropdown
    open_positions = OpenPosition.objects.filter(school=school, is_active=True)

    return render(request, 'users/partials/applications_table.html', {
        'applications': applications,
        'status_filter': status_filter,
        'search': search,
        'position_filter': position_filter,
        'open_positions': open_positions,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
    })


@login_required
def check_email_availability_view(request):
    """HTMX endpoint to check email availability."""
    email = request.POST.get('email', '').strip().lower()
    school = getattr(request, 'school', None)

    if not email:
        return JsonResponse({'error': 'No email provided'}, status=400)

    User = get_user_model()
    Profile = _get_model('Profile')
    StaffInvitation = _get_model('StaffInvitation')

    # Check if user exists globally
    user_exists = User.objects.filter(email=email).exists()

    # Check if user already has access to current school
    school_access = False
    if school and user_exists:
        school_access = Profile.objects.filter(
            user__email=email,
            school=school
        ).exists()

    # Check if pending invitation exists
    pending_invitation = False
    if school:
        pending_invitation = StaffInvitation.objects.filter(
            school=school,
            email=email,
            status='pending'
        ).exists()

    return JsonResponse({
        'email': email,
        'user_exists': user_exists,
        'school_access': school_access,
        'pending_invitation': pending_invitation,
        'available': not school_access and not pending_invitation
    })

# ============ AJAX/JSON ENDPOINTS ============

@login_required
@require_school_context
@require_role('manage_staff')
def staff_toggle_active(request, staff_id: int):
    """HTMX endpoint to toggle staff active status."""
    school = request.school
    Staff = _get_model('Staff')

    staff = get_object_or_404(Staff, id=staff_id, school=school)

    staff.is_active = not staff.is_active
    staff.save()

    # Return just the updated row
    return render(request, 'users/partials/staff_row.html', {'staff': staff})


@login_required
@require_school_context
@require_role('manage_staff')
def staff_invitation_list_partial(request):
    """HTMX endpoint for staff invitations list."""
    school = request.school
    pending_invitations = StaffService.get_pending_invitations(school)

    return render(request, 'users/partials/invitations_list.html', {
        'pending_invitations': pending_invitations
    })


@login_required
@require_school_context
@require_role('manage_roles')
def role_table_partial(request):
    """HTMX endpoint for role table with filters."""
    school = request.school
    Role = _get_model('Role')
    StaffAssignment = _get_model('StaffAssignment')

    roles = Role.objects.filter(school=school).prefetch_related('staffassignment_set')

    # Apply filters
    category_filter = request.GET.get('category', '')
    if category_filter:
        roles = roles.filter(category=category_filter)

    search_query = request.GET.get('search', '')
    if search_query:
        roles = roles.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Get role statistics
    role_stats = {}
    for role in roles:
        role_stats[role.id] = {
            'total_assignments': role.staffassignment_set.filter(is_active=True).count(),
            'is_system_role': role.is_system_role,
        }

    return render(request, 'users/partials/role_table.html', {
        'roles': roles,
        'role_stats': role_stats,
        'search_query': search_query,
        'category_filter': category_filter,
        'role_categories': Role.ROLE_CATEGORIES,
    })


# ============ MISSING BUT USEFUL VIEWS ============

@login_required
@require_school_context
@require_role('manage_staff')
def resend_invitation_view(request, invitation_id: int):
    """Resend a staff invitation."""
    school = request.school
    StaffInvitation = _get_model('StaffInvitation')

    invitation = get_object_or_404(
        StaffInvitation,
        id=invitation_id,
        school=school,
        status='pending'
    )

    try:
        # Use StaffService to resend invitation
        from .services import StaffService
        StaffService.resend_invitation(invitation)

        messages.success(request, f"Invitation resent to {invitation.email}")

        if request.headers.get('HX-Request'):
            pending_invitations = StaffService.get_pending_invitations(school)
            return render(request, 'users/partials/invitations_list.html', {
                'pending_invitations': pending_invitations
            })

    except Exception as e:
        logger.error(f"Failed to resend invitation {invitation_id}: {str(e)}", exc_info=True)
        messages.error(request, f"Failed to resend invitation: {str(e)}")

    return redirect('users:staff_invite')


@login_required
def withdraw_application_view(request, application_id: int):
    """Withdraw a teacher application."""
    TeacherApplication = _get_model('TeacherApplication')

    application = get_object_or_404(
        TeacherApplication,
        id=application_id,
        email=request.user.email
    )

    if application.status != 'pending':
        messages.error(request, "Only pending applications can be withdrawn.")
        return redirect('users:my_applications')

    application.status = 'withdrawn'
    application.status_changed_by = request.user
    application.status_changed_at = timezone.now()
    application.save()

    messages.success(request, f"Application to {application.school.name} has been withdrawn.")

    if request.headers.get('HX-Request'):
        return redirect('users:my_applications')

    return redirect('users:my_applications')


@login_required
@require_school_context
@require_role('manage_staff')
def application_detail_modal(request, application_id: int):
    """HTMX endpoint for application detail modal."""
    school = request.school
    TeacherApplication = _get_model('TeacherApplication')

    application = get_object_or_404(
        TeacherApplication,
        id=application_id,
        school=school
    )

    context = {
        'application': application,
        'school': school,
    }

    return render(request, 'users/partials/application_detail_modal.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def manage_open_positions_view(request):
    """Manage open teaching positions."""
    school = request.school
    OpenPosition = _get_model('OpenPosition')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            title = request.POST.get('title')
            department = request.POST.get('department', '')
            description = request.POST.get('description', '')
            requirements = request.POST.get('requirements', '')

            if title:
                OpenPosition.objects.create(
                    school=school,
                    title=title,
                    department=department,
                    description=description,
                    requirements=requirements,
                    is_active=True
                )
                messages.success(request, f"Position '{title}' created.")

        elif action == 'toggle':
            position_id = request.POST.get('position_id')
            position = get_object_or_404(OpenPosition, id=position_id, school=school)
            position.is_active = not position.is_active
            position.save()

            status = "activated" if position.is_active else "deactivated"
            messages.success(request, f"Position '{position.title}' {status}.")

        elif action == 'delete':
            position_id = request.POST.get('position_id')
            position = get_object_or_404(OpenPosition, id=position_id, school=school)
            position.delete()
            messages.success(request, f"Position '{position.title}' deleted.")

        if request.headers.get('HX-Request'):
            positions = OpenPosition.objects.filter(school=school).order_by('-is_active', 'title')
            return render(request, 'users/partials/open_positions_table.html', {
                'positions': positions
            })

    positions = OpenPosition.objects.filter(school=school).order_by('-is_active', 'title')

    context = {
        'positions': positions,
        'page_title': 'Manage Open Positions'
    }

    return render(request, 'users/manage_open_positions.html', context)


@login_required
@require_school_context
@require_role('manage_staff')
def application_export_view(request):
    """Export applications as CSV or PDF."""
    school = request.school
    TeacherApplication = _get_model('TeacherApplication')

    export_format = request.GET.get('format', 'csv')
    status_filter = request.GET.get('status', '')

    applications = TeacherApplication.objects.filter(school=school)

    if status_filter:
        applications = applications.filter(status=status_filter)

    if export_format == 'csv':
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="applications_{school.subdomain}_{timezone.now().date()}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Name', 'Email', 'Phone', 'Position', 'Experience', 'Qualification', 'Status', 'Applied Date'])

        for app in applications:
            writer.writerow([
                app.full_name,
                app.email,
                app.phone_number,
                app.position_applied,
                app.years_of_experience,
                app.qualification,
                app.get_status_display(),
                app.created_at.strftime('%Y-%m-%d')
            ])

        return response

    elif export_format == 'pdf':
        # For PDF, you'd need to implement this with reportlab or another library
        messages.info(request, "PDF export coming soon. Please use CSV export for now.")
        return redirect('users:school_applications')

    messages.error(request, "Invalid export format.")
    return redirect('users:school_applications')


@login_required
@require_school_context
def staff_export_view(request):
    """Export staff list as CSV."""
    school = request.school
    Staff = _get_model('Staff')

    staff_members = Staff.objects.filter(school=school)

    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="staff_{school.subdomain}_{timezone.now().date()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Staff ID', 'Name', 'Email', 'Phone', 'Position', 'Department', 'Employment Type', 'Date Joined', 'Status'])

    for staff in staff_members:
        writer.writerow([
            staff.staff_id,
            staff.full_name,
            staff.email,
            staff.phone_number,
            staff.position,
            staff.department,
            staff.get_employment_type_display(),
            staff.date_joined.strftime('%Y-%m-%d'),
            'Active' if staff.is_active else 'Inactive'
        ])

    return response


@login_required
@require_school_context
@require_role('manage_staff')
def bulk_staff_actions_view(request):
    """Handle bulk staff actions (activate/deactivate)."""
    school = request.school
    Staff = _get_model('Staff')

    if request.method == 'POST':
        action = request.POST.get('action')
        staff_ids = request.POST.getlist('staff_ids')

        if not staff_ids:
            messages.error(request, "No staff members selected.")
            return redirect('users:staff_list')

        staff_members = Staff.objects.filter(id__in=staff_ids, school=school)

        if action == 'activate':
            staff_members.update(is_active=True)
            messages.success(request, f"{staff_members.count()} staff members activated.")
        elif action == 'deactivate':
            staff_members.update(is_active=False)
            messages.success(request, f"{staff_members.count()} staff members deactivated.")
        elif action == 'delete':
            count = staff_members.count()
            staff_members.delete()
            messages.success(request, f"{count} staff members deleted.")

        if request.headers.get('HX-Request'):
            staff_members = Staff.objects.filter(school=school)
            return render(request, 'users/partials/staff_table.html', {
                'staff_members': staff_members
            })

    return redirect('users:staff_list')
