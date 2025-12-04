# admissions/urls.py - COMPLETE VERSION
from django.urls import path
from . import views

app_name = 'admissions'

urlpatterns = [
    # ===== ADMIN MANAGEMENT ROUTES =====
    path('dashboard/', views.admissions_dashboard_view, name='dashboard'),
    path('applications/', views.application_list_view, name='application_list'),
    path('applications/<int:application_id>/', views.application_detail_view, name='application_detail'),
    path('admissions/', views.admission_list_view, name='admission_list'),
    path('application-forms/', views.manage_application_forms_view, name='manage_application_forms'),
    
    path('applications/<int:application_id>/update/', views.application_update_view, name='application_update'),
    path('applications/<int:application_id>/timeline/', views.application_timeline_partial, name='application_timeline_partial'),
    
    # ===== PUBLIC APPLICATION ROUTES =====
    path('apply/<slug:form_slug>/', views.public_application_start_view, name='public_application_start'),
    path('apply/<slug:form_slug>/form/', views.public_application_form_view, name='public_application_form'),
    path('apply/<slug:form_slug>/submit/', views.public_application_submit_view, name='public_application_submit'),
    path('application-success/<uuid:public_uuid>/', views.application_success_view, name='application_success'),

    path('application-status/<uuid:application_uuid>/', views.public_application_status_view, name='public_application_status'),
    
    # ===== HTMX PARTIALS =====
    path('applications/table/', views.application_table_partial, name='application_table_partial'),
    path('applications/<int:application_id>/timeline/', views.application_timeline_partial, name='application_timeline'),
    path('applications/<int:application_id>/quick-actions/', views.application_quick_actions_view, name='application_quick_actions'),
    path('applications/filters/', views.application_filters_partial, name='application_filters_partial'),
    path('admissions/stats/', views.admission_stats_partial, name='admission_stats_partial'),
    path('apply/<slug:form_slug>/validate-field/', views.validate_application_field_view, name='validate_application_field'),
]