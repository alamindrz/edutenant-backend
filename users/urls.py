# users/urls.py
"""
URL Configuration for Users App
Clean, well-organized URLs following RESTful conventions
"""
from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # ============ DASHBOARD & PROFILE ============
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    
    # ============ SCHOOL MANAGEMENT ============
    path('schools/', views.school_list_view, name='school_list'),
    path('schools/switch/<int:school_id>/', 
         views.switch_school_view, name='switch_school'),
    path('schools/onboarding/', 
         views.school_onboarding_start, name='school_onboarding'),
    
    # ============ STAFF MANAGEMENT ============
    path('staff/', views.staff_list_view, name='staff_list'),
    path('staff/create/', views.staff_create_view, name='staff_create'),
    path('staff/<int:staff_id>/', views.staff_detail_view, name='staff_detail'),
    path('staff/<int:staff_id>/assign-role/', 
         views.assign_role_view, name='assign_role'),
    path('staff/<int:staff_id>/remove-role/<int:assignment_id>/', 
         views.remove_role_assignment, name='remove_role_assignment'),
    path('staff/invite/', views.staff_invite_view, name='staff_invite'),
    
    # ============ ROLE MANAGEMENT ============
    path('roles/', views.role_list_view, name='role_list'),
    path('roles/create/', views.role_create_view, name='role_create'),
    path('roles/<int:role_id>/', views.role_detail_view, name='role_detail'),
    path('roles/<int:role_id>/edit/', views.role_edit_view, name='role_edit'),
    
    # ============ TEACHER APPLICATIONS ============
    path('applications/', views.school_applications_view, name='school_applications'),
    path('applications/<int:application_id>/approve/', 
         views.approve_application_view, name='approve_application'),
    path('applications/<int:application_id>/reject/', 
         views.reject_application_view, name='reject_application'),
    
    # ============ OPEN POSITIONS MANAGEMENT ============
    path('positions/', views.manage_open_positions_view, name='manage_open_positions'),
    
    # ============ SCHOOL DISCOVERY & APPLICATIONS ============
    path('discover/', views.school_discovery_view, name='school_discovery'),
    path('apply/<int:school_id>/', 
         views.apply_to_school_view, name='apply_to_school'),
    path('my-applications/', views.my_applications_view, name='my_applications'),
    path('applications/<int:application_id>/withdraw/', 
         views.withdraw_application_view, name='withdraw_application'),
    
    # ============ INVITATION ACCEPTANCE ============
    path('invitations/accept/<str:token>/', 
         views.accept_invitation_view, name='accept_invitation'),
    
    # ============ EXPORT ENDPOINTS ============
    path('applications/export/', views.application_export_view, name='application_export'),
    path('staff/export/', views.staff_export_view, name='staff_export'),
    
    # ============ AJAX/HTMX ENDPOINTS ============
    # School onboarding
    path('onboarding/check-subdomain/', 
         views.check_subdomain_availability, name='check_subdomain'),
    path('onboarding/validate-school-name/', 
         views.validate_school_name, name='validate_school_name'),
    
    # Staff management
    path('ajax/staff-toggle-active/<int:staff_id>/', 
         views.staff_toggle_active, name='staff_toggle_active'),
    path('ajax/staff-table/', 
         views.staff_table_partial, name='staff_table_partial'),
    path('ajax/staff-bulk-actions/', 
         views.bulk_staff_actions_view, name='staff_bulk_actions'),
    
    # Staff invitations
    path('ajax/cancel-invitation/<int:invitation_id>/', 
         views.cancel_invitation_view, name='cancel_invitation'),
    path('ajax/resend-invitation/<int:invitation_id>/', 
         views.resend_invitation_view, name='resend_invitation'),
    path('ajax/invitations-table/', 
         views.staff_invitation_list_partial, name='staff_invitation_list_partial'),
    
    # Role management
    path('ajax/role-table/', 
         views.role_table_partial, name='role_table_partial'),
    
    # Application management
    path('ajax/applications-table/', 
         views.applications_table_partial, name='applications_table_partial'),
    path('ajax/application-detail/<int:application_id>/', 
         views.application_detail_modal, name='application_detail_modal'),
    
    # Email validation
    path('ajax/check-email/', 
         views.check_email_availability_view, name='check_email_availability'),
    
    # Dashboard components
    path('ajax/dashboard-stats/', 
         views.dashboard_stats_partial, name='dashboard_stats'),
    path('ajax/recent-activity/', 
         views.recent_activity_partial, name='recent_activity'),
]