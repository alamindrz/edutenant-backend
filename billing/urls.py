# billing/urls.py
from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # School Billing Management
    path('dashboard/', views.billing_dashboard_view, name='dashboard'),
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/<int:invoice_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('fee-structures/', views.fee_structure_list_view, name='fee_structure_list'),
    
    # Parent Billing
    path('parent/invoices/', views.parent_invoice_list_view, name='parent_invoices'),
    path('parent/payment/', views.parent_payment_view, name='parent_payment'),
    path('parent/payment/<int:invoice_id>/', views.parent_payment_view, name='parent_payment_single'),
    
    # Payment Callbacks
    path('payment/success/', views.payment_success_view, name='payment_success'),
    path('payment/failed/', views.payment_failed_view, name='payment_failed'),
    
    # Webhooks
    path('webhook/paystack/', views.paystack_webhook_view, name='paystack_webhook'),
    
    # HTMX Endpoints
    path('htmx/invoices/table/', views.invoice_table_partial, name='invoice_table_partial'),
    path('htmx/parent/invoices/table/', views.parent_invoice_table_partial, name='parent_invoice_table_partial'),
]