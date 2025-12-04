# billing/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class SubdomainPlan(models.Model):
    """Subscription plans for school subdomains."""
    PLAN_TIERS = (
        ('basic', 'Basic - Path URL'),
        ('standard', 'Standard - Custom Subdomain'),
        ('premium', 'Premium - Full Branding'),
    )
    
    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=20, choices=PLAN_TIERS, default='basic')
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_students = models.IntegerField(default=100)
    max_staff = models.IntegerField(default=10)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    
    # Nigerian context - popular plan pricing
    popular = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'billing_plan'
        ordering = ['order', 'price_monthly']
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'
        
    def __str__(self):
        return f"{self.name} - ₦{self.price_monthly:,.0f}/month"
    
    def save(self, *args, **kwargs):
        """Log plan creation/updates."""
        if self.pk:
            logger.info(f"Updated subscription plan: {self.name}")
        else:
            logger.info(f"Created new subscription plan: {self.name}")
        super().save(*args, **kwargs)


class FeeCategory(models.Model):
    """Category for organizing fees in Nigerian context."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'billing_feecategory'
        ordering = ['order', 'name']
        verbose_name = 'Fee Category'
        verbose_name_plural = 'Fee Categories'
    
    def __str__(self):
        return self.name


class FeeStructure(models.Model):
    """Fee structure optimized for Nigerian schools."""
    FEE_TYPES = (
        ('tuition', 'Tuition Fee'),
        ('application', 'Application Fee'),
        ('registration', 'Registration Fee'),
        ('pta', 'PTA Levy'),
        ('development', 'Development Levy'),
        ('medical', 'Medical Fee'),
        ('sports', 'Sports Fee'),
        ('textbook', 'Textbook Fee'),
        ('uniform', 'Uniform Fee'),
        ('boarding', 'Boarding Fee'),
        ('transport', 'Transport Fee'),
        ('caution', 'Caution Fee'),
        ('other', 'Other Fee'),
    )
    
    school = models.ForeignKey('users.School', on_delete=models.CASCADE, related_name='fee_structures')
    name = models.CharField(max_length=100)
    fee_type = models.CharField(max_length=20, choices=FEE_TYPES)
    category = models.ForeignKey(FeeCategory, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_required = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    applicable_levels = models.JSONField(default=list, help_text="Levels this fee applies to")
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Nigerian context
    is_government_approved = models.BooleanField(default=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="VAT percentage if applicable")

    class Meta:
        db_table = 'billing_feestructure'
        ordering = ['category__order', 'fee_type', 'amount']
        verbose_name = 'Fee Structure'
        verbose_name_plural = 'Fee Structures'
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['fee_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} - ₦{self.amount:,.2f}"
    
    def save(self, *args, **kwargs):
        """Log fee structure changes."""
        if self.pk:
            logger.info(f"Updated fee structure: {self.name} for school {self.school.name}")
        else:
            logger.info(f"Created fee structure: {self.name} for school {self.school.name}")
        super().save(*args, **kwargs)


class Invoice(models.Model):
    """Invoice system with Nigerian payment context."""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('partially_paid', 'Partially Paid'),
    )
    
    # Core information
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    school = models.ForeignKey('users.School', on_delete=models.CASCADE, related_name='invoices')
    parent = models.ForeignKey('students.Parent', on_delete=models.CASCADE, related_name='invoices')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, null=True, blank=True, related_name='invoices')
    
    # Invoice type for Nigerian context
    invoice_type = models.CharField(
        max_length=20,
        choices=(
            ('application', 'Application Fee'),
            ('school_fees', 'School Fees'),
            ('acceptance', 'Acceptance Fee'),  # Optional
            ('other', 'Other Fees'),
        ),
        default='school_fees'
    )
    
    # Amount breakdown with Nigerian context
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paystack_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Payment tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Nigerian payment context
    term = models.ForeignKey('students.AcademicTerm', on_delete=models.SET_NULL, null=True, blank=True)
    session = models.CharField(max_length=20, blank=True, help_text="Academic session e.g., 2024/2025")
    
    # Audit fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_invoice'
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['parent', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
    
    def __str__(self):
        student_name = self.student.full_name if self.student else "No Student"
        return f"Invoice {self.invoice_number} - {student_name} - ₦{self.total_amount:,.2f}"
    
    def save(self, *args, **kwargs):
        """Generate invoice number and log changes."""
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        if self.pk:
            logger.info(f"Updated invoice {self.invoice_number} - Status: {self.status}")
        else:
            logger.info(f"Created invoice {self.invoice_number} for {self.parent.full_name}")
        
        super().save(*args, **kwargs)
    
    def generate_invoice_number(self):
        """Generate Nigerian-style invoice number."""
        school_code = self.school.subdomain.upper() if self.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        month = timezone.now().strftime('%m')
        unique_id = str(uuid.uuid4().int)[:8]
        
        return f"INV/{school_code}/{year}{month}/{unique_id}"
    
    @property
    def is_overdue(self):
        """Check if invoice is overdue."""
        return self.due_date < timezone.now().date() and self.status in ['sent', 'overdue']
    
    @property
    def days_overdue(self):
        """Calculate days overdue."""
        if self.is_overdue:
            return (timezone.now().date() - self.due_date).days
        return 0


class InvoiceItem(models.Model):
    """Line items for invoices with detailed breakdown."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, null=True, blank=True)
    description = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        db_table = 'billing_invoiceitem'
        verbose_name = 'Invoice Item'
        verbose_name_plural = 'Invoice Items'
    
    def __str__(self):
        return f"{self.description} - ₦{self.amount:,.2f}"
    
    def save(self, *args, **kwargs):
        """Calculate amount and log changes."""
        if self.unit_price and self.quantity:
            self.amount = self.unit_price * self.quantity
        
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """Payment transactions with Paystack integration."""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
        ('abandoned', 'Abandoned'),
    )
    
    # Core information
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='transactions')
    paystack_reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Fee breakdown for Nigerian context
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paystack_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    school_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    metadata = models.JSONField(default=dict)
    paystack_response = models.JSONField(default=dict, help_text="Raw response from Paystack")
    
    # Nigerian payment context
    channel = models.CharField(max_length=50, blank=True, help_text="Payment channel: card, bank, etc.")
    currency = models.CharField(max_length=3, default='NGN')
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_transaction'
        indexes = [
            models.Index(fields=['paystack_reference']),
            models.Index(fields=['invoice', 'status']),
            models.Index(fields=['initiated_at']),
        ]
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-initiated_at']
    
    def __str__(self):
        return f"Transaction {self.paystack_reference} - ₦{self.amount:,.2f} - {self.status}"
    
    def save(self, *args, **kwargs):
        """Log transaction status changes."""
        if self.pk:
            old_status = Transaction.objects.get(pk=self.pk).status
            if old_status != self.status:
                logger.info(f"Transaction {self.paystack_reference} status changed: {old_status} -> {self.status}")
        
        super().save(*args, **kwargs)


class SchoolSubscription(models.Model):
    """School subscription management."""
    STATUS_CHOICES = (
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    )
    
    school = models.OneToOneField('users.School', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubdomainPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trialing')
    
    # Billing period
    billing_period = models.CharField(max_length=10, choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly')
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField()
    
    # Payment information
    paystack_subscription_id = models.CharField(max_length=100, blank=True)
    paystack_customer_code = models.CharField(max_length=100, blank=True)
    
    # Nigerian context
    auto_renew = models.BooleanField(default=True)
    payment_reminder_sent = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'billing_subscription'
        verbose_name = 'School Subscription'
        verbose_name_plural = 'School Subscriptions'
    
    def __str__(self):
        return f"{self.school.name} - {self.plan.name} ({self.status})"
    
    def save(self, *args, **kwargs):
        """Set period end and log subscription changes."""
        if not self.current_period_end:
            if self.billing_period == 'yearly':
                self.current_period_end = self.current_period_start + timezone.timedelta(days=365)
            else:
                self.current_period_end = self.current_period_start + timezone.timedelta(days=30)
        
        if self.pk:
            logger.info(f"Updated subscription for {self.school.name} - Status: {self.status}")
        else:
            logger.info(f"Created subscription for {self.school.name} - Plan: {self.plan.name}")
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        """Check if subscription is currently active."""
        return self.status == 'active' and self.current_period_end > timezone.now()
    
    @property
    def days_remaining(self):
        """Calculate days remaining in subscription."""
        if self.current_period_end > timezone.now():
            return (self.current_period_end - timezone.now()).days
        return 0