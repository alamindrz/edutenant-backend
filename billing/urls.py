from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # School Billing Management
    path('dashboard/', views.billing_dashboard_view, name='dashboard'),
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/create/', views.create_invoice_view, name='create_invoice'),
    path('invoices/<int:invoice_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:invoice_id>/send/', views.send_invoice_view, name='send_invoice'),
    path('invoices/<int:invoice_id>/cancel/', views.cancel_invoice_view, name='cancel_invoice'),
    path('invoices/<int:invoice_id>/mark-paid/', views.mark_invoice_paid_view, name='mark_invoice_paid'),
    path('invoices/<int:invoice_id>/download/', views.download_invoice_view, name='download_invoice'),
    
    # Fee Structure Management
    path('fee-structures/', views.fee_structure_list_view, name='fee_structure_list'),
    path('fee-structures/create/', views.create_fee_view, name='create_fee'),
    path('fee-structures/<int:fee_id>/update/', views.update_fee_view, name='update_fee'),
    path('fee-structures/<int:fee_id>/delete/', views.delete_fee_view, name='delete_fee'),
    path('fee-structures/<int:fee_id>/activate/', views.activate_fee_view, name='activate_fee'),
    path('fee-structures/<int:fee_id>/deactivate/', views.deactivate_fee_view, name='deactivate_fee'),
    
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