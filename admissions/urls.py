# admissions/urls.py
from django.urls import path
from . import views

app_name = 'admissions'
urlpatterns = [
    # Landing/intro page (public_application_start.html)
    path('apply/<slug:form_slug>/', views.application_start_view, name='application_start'),
    
    # Actual application form (apply.html)
    path('apply/<slug:form_slug>/form/', views.apply_view, name='apply'),

    path('application/success/<uuid:public_uuid>/', views.application_success_view, name='application_success'),
    path('status/<uuid:application_uuid>/', views.public_application_status_view, name='public_application_status'),
    
    # ===== PAYMENT VIEWS =====
    path('payment/success/', views.payment_success_view, name='payment_success'),
    path('payment/cancel/', views.payment_cancel_view, name='payment_cancel'),
    path('payment/webhook/', views.payment_webhook_view, name='payment_webhook'),
    
    # ===== DASHBOARD & APPLICATION MANAGEMENT (STAFF) =====
    path('dashboard/', views.admissions_dashboard_view, name='dashboard'),
    path('applications/', views.application_list_view, name='application_list'),
    path('applications/<int:application_id>/', views.application_detail_view, name='application_detail'),
    
    # ===== ADMISSION MANAGEMENT (STAFF) =====
    path('admissions/', views.admission_list_view, name='admission_list'),
    path('admissions/<int:admission_id>/', views.admission_detail_view, name='admission_detail'),
    
    # ===== PAYMENT MANAGEMENT (STAFF) =====
    path('payments/monitoring/', views.payment_monitoring_view, name='payment_monitoring'),
    path('payments/retry/<int:application_id>/', views.retry_payment_view, name='retry_payment'),
    path('payments/waive/<int:application_id>/', views.waive_application_fee_view, name='waive_application_fee'),
    
    # ===== HTMX/AJAX ENDPOINTS =====
    path('ajax/applications-table/', views.application_table_partial, name='application_table_partial'),
    path('ajax/application-actions/<int:application_id>/', views.application_quick_actions_view, name='application_quick_actions'),
    path('ajax/application-filters/', views.application_filters_partial, name='application_filters_partial'),
    path('ajax/admission-stats/', views.admission_stats_partial, name='admission_stats_partial'),
    path('ajax/payment-stats/', views.payment_stats_partial, name='payment_stats_partial'),
]