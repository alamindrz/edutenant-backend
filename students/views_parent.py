# students/views_parent.py
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from billing.models import Invoice
from admissions.models import Application, Admission
from .models import Student
from admissions.models import Application, Admission
from admissions.services import ApplicationService

logger = logging.getLogger(__name__)

@login_required
def parent_applications_view(request):
    """View for parents to see their children's applications."""
    try:
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
        
        all_applications = []
        for profile in parent_profiles:
            parent = profile.parent_profile
            applications = ApplicationService.get_parent_applications(parent)
            all_applications.extend(applications)
        
        # Sort by submission date
        all_applications.sort(key=lambda x: x.submitted_at, reverse=True)
        
        context = {
            'applications': all_applications,
        }
        
        return render(request, 'students/parent_applications.html', context)
        
    except Exception as e:
        logger.error(f"Parent applications view error: {str(e)}")
        messages.error(request, "Error loading applications.")
        return redirect('students:parent_dashboard')

@login_required
def parent_application_detail_view(request, application_id):
    """Parent view of specific application details."""
    try:
        application = get_object_or_404(
            Application.objects.select_related('student', 'form', 'admission'),
            id=application_id
        )
        
        # Verify the parent owns this application
        parent_profiles = request.user.profile_set.filter(
            role__system_role_type='parent',
            parent_profile=application.parent
        )
        
        if not parent_profiles.exists():
            messages.error(request, "You don't have permission to view this application.")
            return redirect('students:parent_applications')
        
        context = {
            'application': application,
            'student': application.student,
        }
        
        return render(request, 'students/parent_application_detail.html', context)
        
    except Exception as e:
        logger.error(f"Parent application detail error: {str(e)}")
        messages.error(request, "Error loading application details.")
        return redirect('students:parent_applications')



@login_required
def parent_dashboard_view(request):
    """Comprehensive parent dashboard showing all children and school-related info."""
    try:
        # Get all parent profiles for the user
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
        
        if not parent_profiles.exists():
            messages.info(request, "You don't have any parent profiles associated with your account.")
            return render(request, 'students/parent_dashboard.html', {})
        
        children_data = []
        total_pending_fees = 0
        total_paid_fees = 0
        
        for profile in parent_profiles:
            parent = profile.parent_profile
            
            # Get all children for this parent
            children = Student.objects.filter(
                parent=parent, 
                is_active=True
            ).select_related('school', 'class_group', 'education_level')
            
            for child in children:
                # Get pending invoices for this child
                pending_invoices = Invoice.objects.filter(
                    student=child,
                    status__in=['sent', 'overdue']
                )
                
                # Get paid invoices for this child
                paid_invoices = Invoice.objects.filter(
                    student=child,
                    status='paid'
                )
                
                # Get applications for this child
                applications = Application.objects.filter(
                    student=child
                ).select_related('form')
                
                # Get admissions for this child
                admissions = Admission.objects.filter(
                    student=child
                ).select_related('offered_class')
                
                child_pending = sum(inv.total_amount for inv in pending_invoices)
                child_paid = sum(inv.total_amount for inv in paid_invoices)
                
                total_pending_fees += child_pending
                total_paid_fees += child_paid
                
                children_data.append({
                    'child': child,
                    'school': child.school,
                    'class_group': child.class_group,
                    'pending_invoices': pending_invoices,
                    'paid_invoices': paid_invoices,
                    'applications': applications,
                    'admissions': admissions,
                    'total_pending': child_pending,
                    'total_paid': child_paid,
                })
        
        # Sort by school then by child name
        children_data.sort(key=lambda x: (x['school'].name, x['child'].first_name))
        
        # Get recent activity across all children
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
        
        logger.info(f"Parent dashboard accessed for user {request.user.email}")
        return render(request, 'students/parent_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Parent dashboard error for user {request.user.id}: {str(e)}")
        messages.error(request, "Error loading your dashboard. Please try again.")
        return render(request, 'students/parent_dashboard.html', {})


@login_required
def parent_children_view(request):
    """View focused on children management for parents."""
    try:
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
        
        children_data = []
        for profile in parent_profiles:
            parent = profile.parent_profile
            children = Student.objects.filter(
                parent=parent
            ).select_related('school', 'class_group', 'education_level').order_by('school__name', 'first_name')
            
            for child in children:
                # Get current academic information
                current_attendance = child.attendance_set.filter(
                    date__gte=timezone.now() - timezone.timedelta(days=30)
                ).order_by('-date')[:5]
                
                children_data.append({
                    'child': child,
                    'school': child.school,
                    'current_attendance': current_attendance,
                    'is_active': child.is_active,
                })
        
        context = {
            'children_data': children_data,
        }
        
        return render(request, 'students/parent_children.html', context)
        
    except Exception as e:
        logger.error(f"Parent children view error: {str(e)}")
        messages.error(request, "Error loading children information.")
        return redirect('students:parent_dashboard')