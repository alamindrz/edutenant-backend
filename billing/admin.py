# billing/admin.py - PRODUCTION READY ADMIN
import json
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

# ✅ Import shared constants
from shared.constants import StatusChoices

from .models import Invoice, Transaction, FeeStructure, SchoolSubscription, InvoiceItem, FeeCategory, SubdomainPlan


@admin.register(SubdomainPlan)
class SubdomainPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'tier', 'price_monthly', 'price_yearly', 'max_students', 'max_staff', 'is_active', 'popular']
    list_filter = ['tier', 'is_active', 'popular']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'popular']

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('order', 'price_monthly')


@admin.register(FeeCategory)
class FeeCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']
    list_editable = ['order']
    search_fields = ['name', 'description']


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'school', 'fee_type', 'amount', 'is_active', 'due_date']
    list_filter = ['fee_type', 'is_active', 'school', 'is_government_approved']
    search_fields = ['name', 'description', 'school__name']
    list_editable = ['is_active', 'amount']
    raw_id_fields = ['school', 'category']

    fieldsets = (
        ('Basic Information', {
            'fields': ('school', 'name', 'fee_type', 'category', 'description')
        }),
        ('Amount & Status', {
            'fields': ('amount', 'is_required', 'is_active', 'due_date')
        }),
        ('Nigerian Context', {
            'fields': ('is_government_approved', 'tax_rate', 'applicable_levels')
        }),
    )


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'school_link', 'student_link', 'invoice_type',
        'total_amount_formatted', 'status_badge', 'due_date', 'paid_date',
        'is_overdue_badge'
    ]
    list_filter = ['status', 'invoice_type', 'school', 'created_at']
    search_fields = ['invoice_number', 'student__first_name', 'student__last_name', 'parent__first_name', 'parent__last_name']
    readonly_fields = ['created_at', 'updated_at', 'paystack_reference', 'invoice_number', 'total_amount']
    date_hierarchy = 'created_at'
    raw_id_fields = ['school', 'parent', 'student', 'term', 'created_by']

    fieldsets = (
        ('Basic Information', {
            'fields': ('invoice_number', 'school', 'parent', 'student', 'invoice_type', 'term', 'session')
        }),
        ('Amount Details', {
            'fields': ('subtotal', 'platform_fee', 'paystack_fee', 'discount', 'tax_amount', 'total_amount')
        }),
        ('Payment Status', {
            'fields': ('status', 'due_date', 'paid_date', 'paystack_reference')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by')
        }),
    )

    def total_amount_formatted(self, obj):
        return f"₦{obj.total_amount:,.2f}"
    total_amount_formatted.short_description = 'Amount'

    def status_badge(self, obj):
        # ✅ Using shared StatusChoices constants
        status_colors = {
            StatusChoices.DRAFT: 'gray',
            StatusChoices.SENT: 'blue',
            StatusChoices.PAID: 'green',
            StatusChoices.OVERDUE: 'orange',
            StatusChoices.CANCELLED: 'red',
            StatusChoices.PARTIALLY_PAID: 'yellow',
        }

        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def is_overdue_badge(self, obj):
        if obj.is_overdue:
            return format_html(
                '<span style="background: red; color: white; padding: 2px 8px; border-radius: 10px;">OVERDUE ({obj.days_overdue} days)</span>'
            )
        return ''
    is_overdue_badge.short_description = 'Overdue'

    def school_link(self, obj):
        if obj.school:
            url = reverse('admin:core_school_change', args=[obj.school.id])
            return format_html('<a href="{}">{}</a>', url, obj.school.name)
        return '-'
    school_link.short_description = 'School'

    def student_link(self, obj):
        if obj.student:
            url = reverse('admin:students_student_change', args=[obj.student.id])
            return format_html('<a href="{}">{}</a>', url, obj.student.full_name)
        return '-'
    student_link.short_description = 'Student'

    def has_delete_permission(self, request, obj=None):
        # ✅ Using shared constant
        if obj and obj.status == StatusChoices.PAID:
            return False
        return super().has_delete_permission(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'school', 'student', 'parent', 'term', 'created_by'
        )


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ['description', 'invoice_link', 'quantity', 'unit_price', 'amount']
    list_filter = ['invoice__school']
    search_fields = ['description', 'invoice__invoice_number']
    raw_id_fields = ['invoice', 'fee_structure']

    def invoice_link(self, obj):
        url = reverse('admin:billing_invoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
    invoice_link.short_description = 'Invoice'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('invoice', 'fee_structure')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'paystack_reference', 'invoice_link', 'amount_formatted',
        'status_badge', 'payment_method_badge', 'channel',
        'initiated_at', 'completed_at'
    ]
    list_filter = ['status', 'initiated_at', 'channel', 'payment_method']
    search_fields = ['paystack_reference', 'invoice__invoice_number', 'metadata']
    readonly_fields = ['initiated_at', 'completed_at', 'created_at', 'updated_at', 'paystack_response_preview']
    raw_id_fields = ['invoice']

    fieldsets = (
        ('Transaction Details', {
            'fields': ('invoice', 'paystack_reference', 'amount', 'status', 'payment_method', 'channel', 'currency')
        }),
        ('Fee Breakdown', {
            'fields': ('platform_fee', 'paystack_fee', 'school_amount')
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'completed_at', 'created_at', 'updated_at')
        }),
        ('Metadata', {
            'fields': ('metadata', 'paystack_response_preview')
        }),
    )

    def amount_formatted(self, obj):
        return f"₦{obj.amount:,.2f}"
    amount_formatted.short_description = 'Amount'

    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse('admin:billing_invoice_change', args=[obj.invoice.id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return '-'
    invoice_link.short_description = 'Invoice'

    def status_badge(self, obj):
        # ✅ Using shared StatusChoices constants
        status_colors = {
            StatusChoices.PENDING: 'orange',
            StatusChoices.SUCCESS: 'green',
            StatusChoices.FAILED: 'red',
            StatusChoices.REVERSED: 'purple',
            StatusChoices.ABANDONED: 'gray',
        }

        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def payment_method_badge(self, obj):
        method_colors = {
            'paystack': 'blue',
            'cash': 'green',
            'transfer': 'purple',
            'waiver': 'gray',
        }

        color = method_colors.get(obj.payment_method, 'gray')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{}</span>',
            color, obj.get_payment_method_display() if hasattr(obj, 'get_payment_method_display') else obj.payment_method
        )
    payment_method_badge.short_description = 'Method'

    def paystack_response_preview(self, obj):
        if obj.paystack_response:
            return format_html(
                '<pre style="max-height: 200px; overflow: auto; background: #f5f5f5; padding: 10px;">{}</pre>',
                json.dumps(obj.paystack_response, indent=2, ensure_ascii=False)
            )
        return '-'
    paystack_response_preview.short_description = 'Paystack Response'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('invoice')


@admin.register(SchoolSubscription)
class SchoolSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'school_link', 'plan', 'status_badge', 'billing_period',
        'current_period_start', 'current_period_end',
        'is_active_badge', 'days_remaining_display'
    ]
    list_filter = ['status', 'billing_period', 'plan', 'auto_renew']
    search_fields = ['school__name', 'paystack_subscription_id', 'paystack_customer_code']
    readonly_fields = ['current_period_start', 'current_period_end', 'days_remaining_display']
    raw_id_fields = ['school', 'plan']

    fieldsets = (
        ('Subscription Details', {
            'fields': ('school', 'plan', 'status', 'billing_period', 'auto_renew')
        }),
        ('Billing Period', {
            'fields': ('current_period_start', 'current_period_end', 'days_remaining_display')
        }),
        ('Paystack Integration', {
            'fields': ('paystack_subscription_id', 'paystack_customer_code')
        }),
        ('Notifications', {
            'fields': ('payment_reminder_sent',)
        }),
    )

    def school_link(self, obj):
        if obj.school:
            url = reverse('admin:core_school_change', args=[obj.school.id])
            return format_html('<a href="{}">{}</a>', url, obj.school.name)
        return '-'
    school_link.short_description = 'School'

    def status_badge(self, obj):
        # ✅ Using shared StatusChoices constants
        status_colors = {
            StatusChoices.TRIALING: 'blue',
            StatusChoices.ACTIVE: 'green',
            StatusChoices.PAST_DUE: 'orange',
            StatusChoices.CANCELLED: 'red',
            StatusChoices.EXPIRED: 'gray',
        }

        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background: green; color: white; padding: 2px 8px; border-radius: 10px;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background: red; color: white; padding: 2px 8px; border-radius: 10px;">INACTIVE</span>'
        )
    is_active_badge.short_description = 'Active'

    def days_remaining_display(self, obj):
        days = obj.days_remaining
        if days > 30:
            color = 'green'
        elif days > 7:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px;">{} days</span>',
            color, days
        )
    days_remaining_display.short_description = 'Days Remaining'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('school', 'plan')
