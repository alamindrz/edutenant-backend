# users/views.py 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.contrib.auth import login
from .services import SchoolOnboardingService, StaffService
from core.exceptions import SchoolOnboardingError, ValidationError
import logging
from .services import StaffService

from django.http import JsonResponse
from django.db.models import Q
from core.decorators import require_role, require_school_context

from .models import Staff, Role, StaffAssignment, Profile, School, StaffInvitation,TeacherApplication, OpenPosition, Staff

from .forms import SchoolCreationForm, TeacherApplicationForm, SchoolOnboardingForm, StaffCreationForm, RoleCreationForm




logger = logging.getLogger(__name__)




@login_required
def dashboard_view(request):
    """Enhanced dashboard with school context recovery."""
    context = {}
    
    # If no school in request, try to recover it
    if not hasattr(request, 'school') or not request.school:
        school = recover_school_context(request)
        if school:
            request.school = school
        else:
            # No school found - redirect to school selection
            messages.warning(request, "Please select a school to continue.")
            return redirect('users:school_list')
    
    school = request.school
    
    try:
        # Get user's profile for this school
        profile = Profile.objects.get(user=request.user, school=school)
        context['user_profile'] = profile
        context['user_role'] = profile.role.name
        
        # Add school statistics
        from students.models import Student, Parent
        from users.models import Staff
        
        context.update({
            'school': school,
            'stats': {
                'total_staff': Staff.objects.filter(school=school, is_active=True).count(),
                'total_students': Student.objects.filter(school=school, is_active=True).count(),
                'total_parents': Parent.objects.filter(school=school).count(),
            }
        })
        
    except Profile.DoesNotExist:
        # User doesn't have access to this school
        messages.error(request, f"You don't have access to {school.name}")
        return redirect('users:school_list')
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        messages.error(request, "Error loading dashboard data")
    
    return render(request, 'dashboard.html', context)

def recover_school_context(request):
    """Recover school context when middleware fails."""
    if hasattr(request, 'user') and request.user.is_authenticated:
        # Method 1: User's current_school
        if hasattr(request.user, 'current_school') and request.user.current_school:
            return request.user.current_school
        
        # Method 2: First profile school
        try:
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                # Update user's current_school for consistency
                request.user.current_school = profile.school
                request.user.save()
                return profile.school
        except Exception as e:
            logger.error(f"School recovery failed: {e}")
    
    return None


# users/views.py - UPDATE THE ONBOARDING VIEW

def school_onboarding_start(request):
    """Start school onboarding process with better error handling."""
    if request.method == 'POST':
        logger.info("Onboarding POST request received")
        
        form = SchoolOnboardingForm(request.POST)
        logger.info(f"Form errors: {form.errors}")
        logger.info(f"Form is valid: {form.is_valid()}")
        
        if form.is_valid():
            try:
                logger.info("Form is valid, creating school...")
                
                # Create school from template
                school = SchoolOnboardingService.create_school_from_template(form.cleaned_data)
                logger.info(f"School created successfully: {school.name}")
                
                # Get the admin user and set backend
                from django.contrib.auth import get_user_model
                User = get_user_model()
                admin_user = User.objects.get(email=form.cleaned_data['admin_email'])
                
                # Set the authentication backend
                admin_user.backend = 'django.contrib.auth.backends.ModelBackend'
                
                # Log in the admin user
                login(request, admin_user)
                
                messages.success(request, f"Welcome to Edusuite! Your school '{school.name}' has been created successfully.")
                return redirect('users:dashboard')
                
            except SchoolOnboardingError as e:
                logger.error(f"SchoolOnboardingError: {e}")
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Unexpected error during onboarding: {e}", exc_info=True)
                messages.error(request, "An error occurred during setup. Please try again or contact support.")
        else:
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
    else:
        form = SchoolOnboardingForm()
    
    context = {
        'form': form,
        'page_title': 'Create Your School'
    }
    return render(request, 'users/school_onboarding.html', context)


def check_subdomain_availability(request):
    """AJAX endpoint to check subdomain availability."""
    from django.http import JsonResponse
    
    subdomain = request.GET.get('subdomain', '').strip().lower()
    
    if not subdomain:
        return JsonResponse({'error': 'No subdomain provided'}, status=400)
    
    # Basic validation
    if len(subdomain) < 3:
        return JsonResponse({'error': 'Subdomain must be at least 3 characters'}, status=400)
    
    if not subdomain.replace('-', '').isalnum():
        return JsonResponse({'error': 'Subdomain can only contain letters, numbers, and hyphens'}, status=400)
    
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


@login_required
def profile_view(request):
    """User profile management view."""
    user_profiles = Profile.objects.filter(user=request.user).select_related('school', 'role')
    
    context = {
        'user_profiles': user_profiles
    }
    return render(request, 'users/profile.html', context)

@login_required
def school_list_view(request):
    """List schools user has access to."""
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
def switch_school_view(request, school_id):
    """Switch current school context for user."""
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
@require_role('manage_school')
def create_school_view(request):
    """View for creating new schools (for platform admins)."""
    if request.method == 'POST':
        form = SchoolCreationForm(request.POST, request.FILES)
        if form.is_valid():
            school = form.save(commit=False)
            school.subdomain_status = 'active'  # Auto-activate for admins
            school.save()
            
            messages.success(request, f"School {school.name} created successfully!")
            return redirect('users:school_list')
    else:
        form = SchoolCreationForm()
    
    context = {'form': form}
    return render(request, 'users/create_school.html', context)
    

# users/views.py - UPDATE staff_list_view

@login_required
@require_school_context
@require_role('manage_staff')
def staff_list_view(request):
    """List all staff members for the current school."""
    school = request.school
    
    # Get staff statistics
    total_staff = Staff.objects.filter(school=school).count()
    active_staff = Staff.objects.filter(school=school, is_active=True).count()
    teaching_staff = Staff.objects.filter(school=school, is_teaching_staff=True, is_active=True).count()
    
    # Get applications count
    from .services import StaffService
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
                messages.success(request, f"Staff member {staff.full_name} created successfully!")
                return redirect('users:staff_list')  # Should redirect here
            except Exception as e:
                print(f"Error creating staff member: {str(e)}")  # Add logging
                messages.error(request, f"Error creating staff member: {str(e)}")
        else:
            print("Form is invalid")  # Add logging
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
def staff_edit_view(request, staff_id):
    """Edit existing staff member."""
    school = request.school
    try:
        staff = Staff.objects.get(id=staff_id, school=school)
    except Staff.DoesNotExist:
        messages.error(request, "Staff member not found.")
        return redirect('users:staff_list')

    if request.method == 'POST':
        form = StaffEditForm(request.POST, instance=staff, school=school)
        if form.is_valid():
            try:
                staff = form.save()
                messages.success(request, f"Staff member {staff.full_name} updated successfully!")
                return redirect('users:staff_list')
            except Exception as e:
                messages.error(request, f"Error updating staff member: {str(e)}")
    else:
        form = StaffEditForm(instance=staff, school=school)

    context = {
        'form': form,
        'page_title': f'Edit {staff.full_name}',
        'staff': staff
    }
    return render(request, 'users/staff_form.html', context) 
    
    
    

@login_required
@require_school_context
@require_role('manage_staff')
def staff_detail_view(request, staff_id):
    """View staff member details."""
    school = request.school
    staff = get_object_or_404(Staff, id=staff_id, school=school)
    assignments = StaffAssignment.objects.filter(staff=staff, is_active=True)
    available_roles = Role.objects.filter(school=school, is_active=True).exclude(
        id__in=assignments.values_list('role_id', flat=True)
    )
    
    context = {
        'staff': staff,
        'assignments': assignments,
        'available_roles': available_roles,
    }
    return render(request, 'users/staff_detail.html', context)

@login_required
@require_school_context
@require_role('manage_staff')
def assign_role_view(request, staff_id):
    """Assign role to staff member."""
    school = request.school
    staff = get_object_or_404(Staff, id=staff_id, school=school)
    
    if request.method == 'POST':
        role_id = request.POST.get('role_id')
        role = get_object_or_404(Role, id=role_id, school=school)
        
        # Check if assignment already exists
        existing_assignment = StaffAssignment.objects.filter(staff=staff, role=role).first()
        if existing_assignment:
            if existing_assignment.is_active:
                messages.warning(request, f"{staff.full_name} already has the {role.name} role.")
            else:
                existing_assignment.is_active = True
                existing_assignment.assigned_by = request.user
                existing_assignment.save()
                messages.success(request, f"{role.name} role reassigned to {staff.full_name}.")
        else:
            StaffAssignment.objects.create(
                staff=staff,
                role=role,
                assigned_by=request.user
            )
            messages.success(request, f"{role.name} role assigned to {staff.full_name}.")
        
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
def remove_role_assignment(request, staff_id, assignment_id):
    """Remove role assignment from staff member."""
    school = request.school
    staff = get_object_or_404(Staff, id=staff_id, school=school)
    assignment = get_object_or_404(StaffAssignment, id=assignment_id, staff=staff)
    
    assignment.is_active = False
    assignment.save()
    
    messages.success(request, f"{assignment.role.name} role removed from {staff.full_name}.")
    return redirect('users:staff_detail', staff_id=staff_id)
    
    
    
@login_required
@require_school_context
@require_role('manage_roles')
def role_list_view(request):
    """List all roles for the current school."""
    school = request.school
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
def role_edit_view(request, role_id):
    """Edit existing role."""
    school = request.school
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
        form = RoleCreationForm(instance=role, initial=initial_data, school=school)
    
    context = {
        'form': form,
        'role': role,
        'page_title': f'Edit Role: {role.name}'
    }
    return render(request, 'users/role_form.html', context)

@login_required
@require_school_context
@require_role('manage_roles')
def role_detail_view(request, role_id):
    """View role details and assignments."""
    school = request.school
    role = get_object_or_404(Role, id=role_id, school=school)
    assignments = StaffAssignment.objects.filter(role=role, is_active=True).select_related('staff')
    
    context = {
        'role': role,
        'assignments': assignments,
        'permissions_display': role.get_permissions_display(),
    }
    return render(request, 'users/role_detail.html', context)
    

@login_required
@require_school_context
@require_role('manage_staff')
def staff_toggle_active(request, staff_id):
    """HTMX endpoint to toggle staff active status."""
    school = request.school
    staff = get_object_or_404(Staff, id=staff_id, school=school)
    
    staff.is_active = not staff.is_active
    staff.save()
    
    # Return just the updated row
    return render(request, 'users/partials/staff_row.html', {'staff': staff})

@login_required
@require_school_context
@require_role('manage_staff') 
def staff_table_partial(request):
    """HTMX endpoint for staff table with filters."""
    school = request.school
    staff_members = Staff.objects.filter(school=school).select_related('user').prefetch_related('staffassignment_set')
    
    # Apply filters (same as staff_list_view)
    active_filter = request.GET.get('active')
    if active_filter is not None:
        staff_members = staff_members.filter(is_active=active_filter.lower() == 'true')
    
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
    


# users/views.py - ADD THESE VIEWS

# ===== TEACHER INVITATION VIEWS =====
@login_required
@require_school_context
@require_role('manage_staff')
def staff_invite_view(request):
    """Invite teachers/staff to join the school."""
    school = request.school
    
    if request.method == 'POST':
        email = request.POST.get('email')
        role_id = request.POST.get('role')
        message = request.POST.get('message', '')
        
        try:
            invitation =  StaffService.invite_teacher(
                school=school,
                invited_by=request.user,
                email=email,
                role_id=role_id,
                message=message
            )
            
            messages.success(request, f"Invitation sent to {email}")
            
            if request.headers.get('HX-Request'):
                # Return updated invitations list for HTMX
                pending_invitations =  StaffService.get_pending_invitations(school)
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
        'pending_invitations':  StaffService.get_pending_invitations(school),
    }
    
    return render(request, 'users/staff_invite.html', context)

def accept_invitation_view(request, token):
    """Accept staff invitation and create account."""
    try:
        invitation = StaffInvitation.objects.get(token=token, status='pending')
        
        if not invitation.is_valid():
            messages.error(request, "This invitation has expired or is no longer valid.")
            return redirect('account_login')
        
        if request.method == 'POST':
            try:
                user_data = {
                    'first_name': request.POST.get('first_name'),
                    'last_name': request.POST.get('last_name'),
                    'phone_number': request.POST.get('phone_number'),
                    'password': request.POST.get('password'),
                }
                
                # Validate passwords match
                if request.POST.get('password') != request.POST.get('password_confirm'):
                    messages.error(request, "Passwords do not match.")
                    return render(request, 'users/accept_invitation.html', {
                        'invitation': invitation
                    })
                
                user =  StaffService.accept_invitation(token, user_data)
                
                # Log the user in
                from django.contrib.auth import login
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                
                messages.success(request, f"Welcome to {invitation.school.name}! Your account has been created.")
                return redirect('users:dashboard')
                
            except ValidationError as e:
                messages.error(request, str(e))
        
        context = {
            'invitation': invitation
        }
        return render(request, 'users/accept_invitation.html', context)
        
    except StaffInvitation.DoesNotExist:
        messages.error(request, "Invalid invitation link.")
        return redirect('account_login')

@login_required
@require_school_context
@require_role('manage_staff')
def staff_invitation_list_partial(request):
    """HTMX endpoint for staff invitations list."""
    school = request.school
    pending_invitations =  StaffService.get_pending_invitations(school)
    
    return render(request, 'users/partials/invitations_list.html', {
        'pending_invitations': pending_invitations
    })

@login_required
@require_school_context
@require_role('manage_staff')
def cancel_invitation_view(request, invitation_id):
    """Cancel a pending invitation."""
    school = request.school
    invitation = get_object_or_404(StaffInvitation, id=invitation_id, school=school, status='pending')
    
    invitation.status = 'expired'
    invitation.save()
    
    messages.success(request, f"Invitation to {invitation.email} has been cancelled.")
    
    if request.headers.get('HX-Request'):
        pending_invitations =  StaffService.get_pending_invitations(school)
        return render(request, 'users/partials/invitations_list.html', {
            'pending_invitations': pending_invitations
        })
    else:
        return redirect('users:staff_invite')

# ===== ENHANCED STAFF MANAGEMENT HTMX VIEWS =====
@login_required
@require_school_context
@require_role('manage_staff')
def staff_quick_edit_view(request, staff_id):
    """HTMX endpoint for quick editing staff details."""
    school = request.school
    staff = get_object_or_404(Staff, id=staff_id, school=school)
    
    if request.method == 'POST':
        field = request.POST.get('field')
        value = request.POST.get('value')
        
        if field in ['position', 'department', 'employment_type']:
            setattr(staff, field, value)
            staff.save()
            
            return render(request, 'users/partials/staff_row.html', {'staff': staff})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@require_school_context
@require_role('manage_staff')
def staff_bulk_actions_view(request):
    """HTMX endpoint for bulk staff actions."""
    school = request.school
    
    if request.method == 'POST':
        action = request.POST.get('action')
        staff_ids = request.POST.getlist('staff_ids')
        
        if action == 'activate':
            Staff.objects.filter(id__in=staff_ids, school=school).update(is_active=True)
            messages.success(request, f"{len(staff_ids)} staff members activated.")
        elif action == 'deactivate':
            Staff.objects.filter(id__in=staff_ids, school=school).update(is_active=False)
            messages.success(request, f"{len(staff_ids)} staff members deactivated.")
        elif action == 'delete':
            Staff.objects.filter(id__in=staff_ids, school=school).delete()
            messages.success(request, f"{len(staff_ids)} staff members deleted.")
        
        # Return updated staff table
        staff_members = Staff.objects.filter(school=school)
        return render(request, 'users/partials/staff_table.html', {
            'staff_members': staff_members
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# ===== ENHANCED ROLE MANAGEMENT HTMX VIEWS =====
@login_required
@require_school_context
@require_role('manage_roles')
def role_table_partial(request):
    """HTMX endpoint for role table with filters."""
    school = request.school
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

@login_required
@require_school_context
@require_role('manage_roles')
def role_quick_create_view(request):
    """HTMX endpoint for quick role creation."""
    school = request.school
    
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        
        if name and category:
            # Check if role already exists
            if Role.objects.filter(school=school, name=name).exists():
                return JsonResponse({'error': 'Role with this name already exists'}, status=400)
            
            role = Role.objects.create(
                name=name,
                category=category,
                school=school,
                description=request.POST.get('description', ''),
                is_system_role=False
            )
            
            return render(request, 'users/partials/role_row.html', {
                'role': role,
                'role_stats': {'total_assignments': 0, 'is_system_role': False}
            })
    
    return JsonResponse({'error': 'Invalid data'}, status=400)

@login_required
@require_school_context
@require_role('manage_roles')
def role_toggle_permission_view(request, role_id):
    """HTMX endpoint to toggle role permissions."""
    school = request.school
    role = get_object_or_404(Role, id=role_id, school=school)
    
    if role.is_system_role:
        return JsonResponse({'error': 'Cannot modify system roles'}, status=400)
    
    permission_field = request.POST.get('permission_field')
    if permission_field in [
        'can_manage_roles', 'can_manage_staff', 'can_manage_students',
        'can_manage_academics', 'can_manage_finances', 'can_view_reports', 'can_communicate'
    ]:
        current_value = getattr(role, permission_field)
        setattr(role, permission_field, not current_value)
        
        # Update permissions list
        permission_map = {
            'can_manage_roles': 'manage_roles',
            'can_manage_staff': 'manage_staff',
            'can_manage_students': 'manage_students',
            'can_manage_academics': 'manage_academics',
            'can_manage_finances': 'manage_finances',
            'can_view_reports': 'view_reports',
            'can_communicate': 'communicate',
        }
        
        permissions = []
        for field, perm in permission_map.items():
            if getattr(role, field):
                permissions.append(perm)
        
        role.permissions = permissions
        role.save()
        
        return render(request, 'users/partials/role_permissions.html', {'role': role})
    
    return JsonResponse({'error': 'Invalid permission field'}, status=400)

# ===== DASHBOARD HTMX VIEWS =====
@login_required
@require_school_context
def dashboard_stats_partial(request):
    """HTMX endpoint for dashboard statistics."""
    school = request.school
    
    from students.models import Student, Parent
    from core.models import Class
    
    stats = {
        'total_staff': Staff.objects.filter(school=school, is_active=True).count(),
        'total_students': Student.objects.filter(school=school, is_active=True).count(),
        'total_parents': Parent.objects.filter(school=school).count(),
        'total_classes': Class.objects.filter(school=school, is_active=True).count(),
        'pending_invitations': StaffInvitation.objects.filter(
            school=school, status='pending'
        ).count(),
    }
    
    return render(request, 'partials/dashboard_stats.html', {
        'stats': stats,
        'school': school
    })

@login_required
@require_school_context
def recent_activity_partial(request):
    """HTMX endpoint for recent activity feed."""
    school = request.school
    
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
    
    
# users/views.py - ADD THIS UTILITY VIEW
@login_required
def check_email_availability(request):
    """HTMX endpoint to check email availability."""
    email = request.POST.get('email', '').strip().lower()
    school = getattr(request, 'school', None)
    
    if not email:
        return JsonResponse({'error': 'No email provided'}, status=400)
    
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
    
    
# users/views.py - ADD HTMX VALIDATION ENDPOINTS

def validate_school_name(request):
    """HTMX endpoint to validate school name."""
    school_name = request.POST.get('school_name', '').strip()
    
    if not school_name:
        return JsonResponse({'valid': False, 'error': 'School name is required'})
    
    from .models import School
    if School.objects.filter(name__iexact=school_name).exists():
        return JsonResponse({
            'valid': False, 
            'error': 'A school with this name already exists'
        })
    
    return JsonResponse({'valid': True})

def validate_password(request):
    """HTMX endpoint to validate password strength."""
    password = request.POST.get('password', '')
    
    if len(password) < 8:
        return JsonResponse({
            'valid': False,
            'error': 'Password must be at least 8 characters'
        })
    
    if password.isnumeric():
        return JsonResponse({
            'valid': False, 
            'error': 'Password cannot be entirely numeric'
        })
    
    return JsonResponse({'valid': True})

def check_email_availability(request):
    """HTMX endpoint to check email availability."""
    email = request.POST.get('email', '').strip().lower()
    
    if not email:
        return JsonResponse({'valid': False, 'error': 'Email is required'})
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    if User.objects.filter(email=email).exists():
        return JsonResponse({
            'valid': False,
            'error': 'A user with this email already exists'
        })
    
    return JsonResponse({'valid': True})
    
    
@login_required
def school_discovery_view(request):
    """View for teachers to discover and search schools."""
    query = request.GET.get('q', '')
    school_type = request.GET.get('school_type', '')
    
    # Get schools with application forms and open positions
    schools = School.objects.filter(
        is_active=True
    ).prefetch_related(
        'openposition_set',
        'application_forms'
    ).annotate(
        open_positions_count=Count('openposition', filter=Q(openposition__is_active=True)),
        open_application_forms_count=Count('application_forms', filter=Q(application_forms__status='active'))
    )
    
    # Apply filters
    if query:
        schools = schools.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(subdomain__icontains=query)
        )
    
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
def apply_to_school_view(request, school_id):
    """View for teachers to apply to a specific school."""
    school = get_object_or_404(School, id=school_id, is_active=True)
    
    # Check if user already has a pending application
    existing_application = TeacherApplication.objects.filter(
        school=school,
        email=request.user.email,
        status='pending'
    ).exists()
    
    if existing_application:
        messages.warning(request, f"You already have a pending application for {school.name}.")
        return redirect('school_feed')
    
    # Check if school has open positions
    open_positions = school.openposition_set.filter(is_active=True)
    if not open_positions.exists():
        messages.error(request, f"{school.name} is not currently hiring teachers.")
        return redirect('school_feed')
    
    if request.method == 'POST':
        form = TeacherApplicationForm(request.POST, request.FILES, school=school)
        if form.is_valid():
            try:
                application_data = form.cleaned_data.copy()
                if application_data.get('position_id'):
                    application_data['position_id'] = int(application_data['position_id'])
                
                # Create the application
                application = TeacherApplication.objects.create(
                    school=school,
                    applicant=request.user,
                    email=application_data['email'],
                    first_name=application_data['first_name'],
                    last_name=application_data['last_name'],
                    phone_number=application_data.get('phone_number', ''),
                    application_type=application_data.get('application_type', 'experienced'),
                    position_applied=application_data.get('position_applied', 'Teacher'),
                    years_of_experience=application_data.get('years_of_experience', 0),
                    qualification=application_data.get('qualification', ''),
                    specialization=application_data.get('specialization', ''),
                    cover_letter=application_data.get('cover_letter', ''),
                    resume=application_data.get('resume'),
                    certificates=application_data.get('certificates'),
                )
                
                messages.success(request, 
                    f"Your application has been submitted to {school.name}! " 
                    "The school administration will review your application and contact you."
                )
                return redirect('users:my_applications')  # FIXED: Use namespace
                    
            except Exception as e:
                messages.error(request, f"Error submitting application: {str(e)}")
    else:
        # Pre-fill form with user data
        initial = {
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'phone_number': request.user.phone_number,
        }
        form = TeacherApplicationForm(school=school, initial=initial)
    
    context = {
        'school': school,
        'form': form,
        'open_positions': open_positions,
        'page_title': f'Apply to {school.name}'
    }
    return render(request, 'users/apply_to_school.html', context)




def my_applications_view(request):
    """Display user's applications."""
    applications = ApplicationService.get_applications_by_user(request.user)
    
    # Group by school for better organization
    applications_by_school = {}
    for app in applications:
        school_id = app.form.school.id
        if school_id not in applications_by_school:
            applications_by_school[school_id] = {
                'school': app.form.school,
                'applications': []
            }
        applications_by_school[school_id]['applications'].append(app)
    
    context = {
        'applications_by_school': applications_by_school,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(status__in=['submitted', 'under_review']).count(),
    }
    
    return render(request, 'users/my_applications.html', context)





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
def approve_application_view(request, application_id):
    """Approve a teacher application."""
    school = request.school
    application = get_object_or_404(TeacherApplication, id=application_id, school=school)
    
    try:
        staff = application.approve(approved_by=request.user)
        messages.success(request, f"Application approved! Staff account created for {staff.full_name}")
        
        # Return HTMX response if needed
        if request.headers.get('HX-Request'):
            applications = StaffService.get_pending_applications(school)
            return render(request, 'users/partials/applications_table.html', {
                'applications': applications
            })
            
    except Exception as e:
        logger.error(f"Failed to approve application {application_id}: {str(e)}")
        messages.error(request, f"Failed to approve application: {str(e)}")
        
        # If it's a role-related error, suggest running the fix command
        if "Role matching query does not exist" in str(e):
            messages.info(request, "System roles missing. Please contact administrator to run role setup.")
    
    return redirect('users:school_applications')




@login_required
@require_school_context
@require_role('manage_staff')
def reject_application_view(request, application_id):
    """Reject a teacher application."""
    school = request.school
    application = get_object_or_404(TeacherApplication, id=application_id, school=school)
    
    reason = request.POST.get('reason', '')
    application.reject(rejected_by=request.user, reason=reason)
    
    messages.success(request, f"Application from {application.full_name} has been rejected.")
    return redirect('users:school_applications')
    
    
    

@login_required
@require_school_context
@require_role('manage_staff')
def applications_table_partial(request):
    """HTMX endpoint for applications table."""
    school = request.school
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
            Q(teacher__first_name__icontains=search) |
            Q(teacher__last_name__icontains=search) |
            Q(teacher__email__icontains=search) |
            Q(position__title__icontains=search)
        )
    
    if position_filter:
        applications = applications.filter(position__title=position_filter)
    
    # Get counts for statistics
    pending_count = applications.filter(status='pending').count()
    approved_count = applications.filter(status='approved').count()
    rejected_count = applications.filter(status='rejected').count()
    
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
@require_school_context
@require_role('manage_staff')
def application_detail_modal(request, application_id):
    """HTMX endpoint for application detail modal content."""
    school = request.school
    application = get_object_or_404(TeacherApplication, id=application_id, school=school)
    
    context = {
        'application': application
    }
    return render(request, 'users/partials/application_detail_modal.html', context)    
    
@login_required
@require_school_context
@require_role('manage_staff')
def invitations_table_partial(request):
    """HTMX endpoint for invitations table."""
    school = request.school
    invitations =  StaffService.get_pending_invitations(school)
    
    return render(request, 'users/partials/invitations_table.html', {
        'invitations': invitations,
    })

@login_required
@require_school_context
@require_role('manage_staff')
def manage_open_positions_view(request):
    """Manage open teaching positions."""
    school = request.school
    
    if request.method == 'POST':
        title = request.POST.get('title')
        department = request.POST.get('department', '')
        description = request.POST.get('description', '')
        requirements = request.POST.get('requirements', '')
        
        if title:
            position = OpenPosition.objects.create(
                school=school,
                title=title,
                department=department,
                description=description,
                requirements=requirements
            )
            messages.success(request, f"Open position '{title}' created successfully!")
            return redirect('users:manage_open_positions')
    
    positions = OpenPosition.objects.filter(school=school)
    
    context = {
        'positions': positions,
        'page_title': 'Manage Open Positions'
    }
    return render(request, 'users/manage_positions.html', context)




@login_required
@require_school_context
@require_role('manage_staff')
def toggle_position_status(request, position_id):
    """HTMX endpoint to toggle position active status."""
    school = request.school
    position = get_object_or_404(OpenPosition, id=position_id, school=school)
    
    if request.method == 'POST':
        position.is_active = not position.is_active
        position.save()
        
        positions = OpenPosition.objects.filter(school=school)
        return render(request, 'users/partials/positions_table.html', {
            'positions': positions
        })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)





@login_required
@require_school_context
@require_role('manage_staff')
def delete_position(request, position_id):
    """Delete an open position."""
    school = request.school
    position = get_object_or_404(OpenPosition, id=position_id, school=school)
    
    position_title = position.title
    position.delete()
    
    messages.success(request, f"Position '{position_title}' deleted successfully!")
    
    if request.headers.get('HX-Request'):
        positions = OpenPosition.objects.filter(school=school)
        return render(request, 'users/partials/positions_table.html', {
            'positions': positions
        })
    else:
        return redirect('users:manage_open_positions')
        

@login_required
@require_school_context
@require_role('manage_finances')
def fee_policies_view(request):
    """View and update school fee policies."""
    school = request.school
    
    if request.method == 'POST':
        # Update fee policies
        school.application_fee_required = request.POST.get('application_fee_required') == 'on'
        school.application_fee_amount = request.POST.get('application_fee_amount', 0)
        
        # Staff children policies
        school.staff_children_waive_application_fee = request.POST.get('staff_children_waive_application_fee') == 'on'
        school.staff_children_discount_percentage = request.POST.get('staff_children_discount_percentage', 0)
        school.staff_children_max_discount = request.POST.get('staff_children_max_discount', 0)
        
        # Scholarship policies
        school.scholarship_enabled = request.POST.get('scholarship_enabled') == 'on'
        school.scholarship_application_required = request.POST.get('scholarship_application_required') == 'on'
        school.scholarship_max_percentage = request.POST.get('scholarship_max_percentage', 100)
        
        # Application policies
        school.allow_staff_applications = request.POST.get('allow_staff_applications') == 'on'
        school.allow_external_applications = request.POST.get('allow_external_applications') == 'on'
        
        school.save()
        messages.success(request, "Fee policies updated successfully.")
        return redirect('users:settings_fees')
    
    context = {
        'school': school,
        'active_tab': 'fees',
    }
    
    return render(request, 'users/settings/fee_policies.html', context)