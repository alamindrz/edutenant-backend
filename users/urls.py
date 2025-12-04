# users/urls.py - COMPLETE UPDATED VERSION
from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Profile & School Management
    path('', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('schools/', views.school_list_view, name='school_list'),
    path('switch-school/<int:school_id>/', views.switch_school_view, name='switch_school'),
    
    # Onboarding
    path('onboarding/', views.school_onboarding_start, name='school_onboarding'),
    path('onboarding/check-subdomain/', views.check_subdomain_availability, name='check_subdomain'),
    
    # HTMX Validation Endpoints
    path('onboarding/validate-school-name/', views.validate_school_name, name='validate_school_name'),
    path('onboarding/validate-password/', views.validate_password, name='validate_password'),
    path('onboarding/check-email/', views.check_email_availability, name='check_email_availability'),

    # Staff Management
    path('staff/', views.staff_list_view, name='staff_list'),
    path('staff/create/', views.staff_create_view, name='staff_create'),
    path('staff/invite/', views.staff_invite_view, name='staff_invite'),
    path('staff/<int:staff_id>/', views.staff_detail_view, name='staff_detail'),
    path('staff/<int:staff_id>/edit/', views.staff_edit_view, name='staff_edit'),
    path('staff/<int:staff_id>/assign-role/', views.assign_role_view, name='assign_role'),
    path('staff/<int:staff_id>/remove-role/<int:assignment_id>/', views.remove_role_assignment, name='remove_role_assignment'),
    
    # Teacher Invitation System
    path('invitations/accept/<str:token>/', views.accept_invitation_view, name='accept_invitation'),
    path('staff/invitations/cancel/<int:invitation_id>/', views.cancel_invitation_view, name='cancel_invitation'),
    
    # HTMX Staff Endpoints
    path('staff/table/', views.staff_table_partial, name='staff_table_partial'),
    path('staff/<int:staff_id>/toggle-active/', views.staff_toggle_active, name='staff_toggle_active'),
    path('staff/<int:staff_id>/quick-edit/', views.staff_quick_edit_view, name='staff_quick_edit'),
    path('staff/bulk-actions/', views.staff_bulk_actions_view, name='staff_bulk_actions'),
    path('staff/invitations/list/', views.staff_invitation_list_partial, name='staff_invitation_list'),
    
    # Role Management
    path('roles/', views.role_list_view, name='role_list'),
    path('roles/create/', views.role_create_view, name='role_create'),
    path('roles/<int:role_id>/', views.role_detail_view, name='role_detail'),
    path('roles/<int:role_id>/edit/', views.role_edit_view, name='role_edit'),
    
    # HTMX Role Endpoints
    path('roles/table/', views.role_table_partial, name='role_table_partial'),
    path('roles/quick-create/', views.role_quick_create_view, name='role_quick_create'),
    path('roles/<int:role_id>/toggle-permission/', views.role_toggle_permission_view, name='role_toggle_permission'),
    
    # HTMX Dashboard Endpoints
    path('dashboard/stats/', views.dashboard_stats_partial, name='dashboard_stats'),
    path('dashboard/activity/', views.recent_activity_partial, name='recent_activity'),
    
    # Email Validation
    path('check-email/', views.check_email_availability, name='check_email'),
    
    # Staff applications
    path('applications/', views.school_applications_view, name='school_applications'),
    path('applications/table/', views.applications_table_partial, name='applications_table_partial'),
    path('applications/<int:application_id>/approve/', views.approve_application_view, name='approve_application'),
    
    path('applications/<int:application_id>/detail/', views.application_detail_modal, name='application_detail_modal'),
    
    path('applications/<int:application_id>/reject/', views.reject_application_view, name='reject_application'),
    
    # Open positions
    path('positions/', views.manage_open_positions_view, name='manage_open_positions'),
    path('positions/<int:position_id>/toggle/', views.toggle_position_status, name='toggle_position_status'),
    path('positions/<int:position_id>/delete/', views.delete_position, name='delete_position'),
    
    # Invitations
    path('invitations/table/', views.invitations_table_partial, name='invitations_table_partial'),
    
    path('my-applications/', views.my_applications_view, name='my_applications'),
    path('apply-to-school/<int:school_id>/', views.apply_to_school_view, name='apply_to_school'),
]