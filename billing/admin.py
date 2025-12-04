# billing/admin.py - PRODUCTION READY ADMIN
from django.contrib import admin
from django.utils.html import format_html
from .models import Invoice, Transaction, FeeStructure, SchoolSubscription

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'school', 'student', 'invoice_type', 
        'total_amount', 'status', 'due_date', 'paid_date'
    ]
    list_filter = ['status', 'invoice_type', 'school', 'created_at']
    search_fields = ['invoice_number', 'student__first_name', 'student__last_name']
    readonly_fields = ['created_at', 'updated_at', 'paystack_reference']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('invoice_number', 'school', 'parent', 'student', 'invoice_type')
        }),
        ('Amount Details', {
            'fields': ('subtotal', 'platform_fee', 'paystack_fee', 'total_amount')
        }),
        ('Payment Status', {
            'fields': ('status', 'due_date', 'paid_date', 'paystack_reference')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by')
        }),
    )
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of paid invoices
        if obj and obj.status == 'paid':
            return False
        return super().has_delete_permission(request, obj)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'paystack_reference', 'invoice_link', 'amount', 
        'status_badge', 'initiated_at', 'completed_at'
    ]
    list_filter = ['status', 'initiated_at', 'channel']
    search_fields = ['paystack_reference', 'invoice__invoice_number']
    readonly_fields = ['initiated_at', 'completed_at', 'paystack_response_preview']
    
    def invoice_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            f'/admin/billing/invoice/{obj.invoice.id}/change/',
            obj.invoice.invoice_number
        )
    invoice_link.short_description = 'Invoice'
    
    def status_badge(self, obj):
        color = {
            'success': 'green', 
            'pending': 'orange', 
            'failed': 'red'
        }.get(obj.status, 'gray')
        
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def paystack_response_preview(self, obj):
        return format_html(
            '<pre style="max-height: 200px; overflow: auto;">{}</pre>',
            json.dumps(obj.paystack_response, indent=2)
        )
    paystack_response_preview.short_description = 'Paystack Response'