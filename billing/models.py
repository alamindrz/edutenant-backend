# billing/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
import logging

# ✅ Import shared constants
from shared.constants import StatusChoices, PaymentMethods

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
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['tier']),
        ]
        
    def __str__(self):
        return f"{self.name} - ₦{self.price_monthly:,.0f}/month"
    
    def clean(self):
        """Validate plan data."""
        from django.core.exceptions import ValidationError
        
        # Validate prices
        if self.price_monthly < 0:
            raise ValidationError({'price_monthly': 'Monthly price cannot be negative.'})
        
        if self.price_yearly < 0:
            raise ValidationError({'price_yearly': 'Yearly price cannot be negative.'})
        
        # Validate max counts
        if self.max_students <= 0:
            raise ValidationError({'max_students': 'Maximum students must be positive.'})
        
        if self.max_staff <= 0:
            raise ValidationError({'max_staff': 'Maximum staff must be positive.'})
    
    def save(self, *args, **kwargs):
        """Save plan with validation."""
        self.full_clean()
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
    
    # ✅ Using 'core.School' - correct
    school = models.ForeignKey('core.School', on_delete=models.CASCADE, related_name='fee_structures')
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
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.name} - ₦{self.amount:,.2f}"
    
    def clean(self):
        """Validate fee structure data."""
        from django.core.exceptions import ValidationError
        
        # Validate amount
        if self.amount < 0:
            raise ValidationError({'amount': 'Fee amount cannot be negative.'})
        
        # Validate tax rate
        if self.tax_rate < 0 or self.tax_rate > 100:
            raise ValidationError({'tax_rate': 'Tax rate must be between 0 and 100.'})
        
        # Validate due date if provided
        if self.due_date and self.due_date < timezone.now().date():
            raise ValidationError({'due_date': 'Due date cannot be in the past.'})
    
    def save(self, *args, **kwargs):
        """Save fee structure with validation."""
        self.full_clean()
        super().save(*args, **kwargs)


class Invoice(models.Model):
    """Invoice system with Nigerian payment context."""
    # ✅ Using shared StatusChoices for consistency
    STATUS_CHOICES = (
        (StatusChoices.DRAFT, 'Draft'),
        (StatusChoices.SENT, 'Sent'),
        (StatusChoices.PAID, 'Paid'),
        (StatusChoices.OVERDUE, 'Overdue'),
        (StatusChoices.CANCELLED, 'Cancelled'),
        (StatusChoices.PARTIALLY_PAID, 'Partially Paid'),
    )
    
    # Core information
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    # ✅ Using 'core.School' - correct
    school = models.ForeignKey('core.School', on_delete=models.CASCADE, related_name='invoices')
    parent = models.ForeignKey('students.Parent', on_delete=models.CASCADE, related_name='invoices')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, null=True, blank=True, related_name='invoices')
    
    # Invoice type for Nigerian context
    invoice_type = models.CharField(
        max_length=20,
        choices=(
            ('application', 'Application Fee'),
            ('school_fees', 'School Fees'),
            ('acceptance', 'Acceptance Fee'),
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
    
    # Payment tracking - using shared constants
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=StatusChoices.DRAFT)
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
            models.Index(fields=['student', 'status']),
            models.Index(fields=['due_date', 'status']),
            models.Index(fields=['invoice_type']),
        ]
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-created_at']
    
    def __str__(self):
        student_name = self.student.full_name if self.student else "No Student"
        return f"Invoice {self.invoice_number} - {student_name} - ₦{self.total_amount:,.2f}"
    
    def clean(self):
        """Validate invoice data."""
        from django.core.exceptions import ValidationError
        
        # Validate amounts
        if self.subtotal < 0:
            raise ValidationError({'subtotal': 'Subtotal cannot be negative.'})
        
        if self.total_amount < 0:
            raise ValidationError({'total_amount': 'Total amount cannot be negative.'})
        
        # Validate discount
        if self.discount < 0:
            raise ValidationError({'discount': 'Discount cannot be negative.'})
        
        if self.discount > self.subtotal:
            raise ValidationError({'discount': 'Discount cannot exceed subtotal.'})
        
        # Validate due date
        if self.due_date and self.due_date < timezone.now().date():
            raise ValidationError({'due_date': 'Due date cannot be in the past for new invoices.'})
        
        # Validate school consistency
        if self.parent and self.parent.school != self.school:
            raise ValidationError({
                'parent': 'Parent must belong to the same school.'
            })
        
        if self.student and self.student.school != self.school:
            raise ValidationError({
                'student': 'Student must belong to the same school.'
            })
        
        # Validate academic term if provided
        if self.term and self.term.school != self.school:
            raise ValidationError({
                'term': 'Academic term must belong to the same school.'
            })
    
    def save(self, *args, **kwargs):
        """Save invoice with auto-generated number and validation."""
        self.full_clean()  # Run validation first
        
        # Generate invoice number if not provided
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        # Ensure total amount is calculated if not set
        if not self.total_amount and self.subtotal:
            self.total_amount = self.subtotal + self.platform_fee + self.paystack_fee + self.tax_amount - self.discount
        
        super().save(*args, **kwargs)
    
    def generate_invoice_number(self):
        """Generate Nigerian-style invoice number."""
        school_code = self.school.subdomain.upper()[:3] if self.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        month = timezone.now().strftime('%m')
        unique_id = str(uuid.uuid4().int)[:8]
        
        return f"INV/{school_code}/{year}{month}/{unique_id}"
    
    @property
    def is_overdue(self):
        """Check if invoice is overdue."""
        return (
            self.due_date < timezone.now().date() and 
            self.status in [StatusChoices.SENT, StatusChoices.OVERDUE, StatusChoices.PARTIALLY_PAID]
        )
    
    @property
    def days_overdue(self):
        """Calculate days overdue."""
        if self.is_overdue:
            return (timezone.now().date() - self.due_date).days
        return 0
    
    @property
    def amount_due(self):
        """Calculate amount due (total - payments)."""
        payments = sum(
            t.amount for t in self.transactions.filter(status=StatusChoices.SUCCESS)
        )
        return max(Decimal('0'), self.total_amount - payments)
    
    @property
    def is_fully_paid(self):
        """Check if invoice is fully paid."""
        return self.amount_due <= 0


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
        indexes = [
            models.Index(fields=['invoice']),
        ]
    
    def __str__(self):
        return f"{self.description} - ₦{self.amount:,.2f}"
    
    def clean(self):
        """Validate invoice item data."""
        from django.core.exceptions import ValidationError
        
        # Validate quantities and prices
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be positive.'})
        
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})
        
        # Validate fee_structure belongs to same school
        if self.fee_structure and self.invoice and self.fee_structure.school != self.invoice.school:
            raise ValidationError({
                'fee_structure': 'Fee structure must belong to the same school as the invoice.'
            })
    
    def save(self, *args, **kwargs):
        """Calculate amount and validate."""
        self.full_clean()
        
        # Auto-calculate amount if not set
        if not self.amount and self.unit_price and self.quantity:
            self.amount = self.unit_price * self.quantity
        
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """Payment transactions with Paystack integration."""
    # ✅ Using shared StatusChoices
    STATUS_CHOICES = (
        (StatusChoices.PENDING, 'Pending'),
        (StatusChoices.SUCCESS, 'Success'),
        (StatusChoices.FAILED, 'Failed'),
        (StatusChoices.REVERSED, 'Reversed'),
        (StatusChoices.ABANDONED, 'Abandoned'),
    )
    
    # Core information
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='transactions')
    paystack_reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Fee breakdown for Nigerian context
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paystack_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    school_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status and metadata - using shared constants
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=StatusChoices.PENDING)
    metadata = models.JSONField(default=dict)
    paystack_response = models.JSONField(default=dict, help_text="Raw response from Paystack")
    
    # ✅ Using shared PaymentMethods constant for payment method field (add this)
    payment_method = models.CharField(
        max_length=20, 
        choices=PaymentMethods.choices if hasattr(PaymentMethods, 'choices') else [
            ('paystack', 'Paystack'),
            ('cash', 'Cash'),
            ('transfer', 'Transfer'),
            ('waiver', 'Waiver'),
        ],
        default='paystack'
    )
    
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
            models.Index(fields=['status', 'completed_at']),
            models.Index(fields=['payment_method']),  # Added index
        ]
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-initiated_at']
    
    def __str__(self):
        return f"Transaction {self.paystack_reference} - ₦{self.amount:,.2f} - {self.status}"
    
    def clean(self):
        """Validate transaction data."""
        from django.core.exceptions import ValidationError
        
        # Validate amount
        if self.amount <= 0:
            raise ValidationError({'amount': 'Transaction amount must be positive.'})
        
        # Validate school_amount calculation
        if self.school_amount < 0:
            raise ValidationError({'school_amount': 'School amount cannot be negative.'})
        
        # Validate currency
        if self.currency != 'NGN':
            raise ValidationError({'currency': 'Only NGN currency is supported.'})
        
        # Auto-calculate school_amount if not set
        if not self.school_amount and self.amount and self.platform_fee and self.paystack_fee:
            self.school_amount = self.amount - self.platform_fee - self.paystack_fee
    
    def save(self, *args, **kwargs):
        """Save transaction with validation."""
        self.full_clean()
        super().save(*args, **kwargs)


class SchoolSubscription(models.Model):
    """School subscription management."""
    # ✅ Using shared StatusChoices
    STATUS_CHOICES = (
        (StatusChoices.TRIALING, 'Trialing'),
        (StatusChoices.ACTIVE, 'Active'),
        (StatusChoices.PAST_DUE, 'Past Due'),
        (StatusChoices.CANCELLED, 'Cancelled'),
        (StatusChoices.EXPIRED, 'Expired'),
    )
    
    # ✅ Using 'core.School' - correct
    school = models.OneToOneField('core.School', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubdomainPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=StatusChoices.TRIALING)
    
    # Billing period
    billing_period = models.CharField(
        max_length=10, 
        choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], 
        default='monthly'
    )
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
        indexes = [
            models.Index(fields=['school']),
            models.Index(fields=['status']),
            models.Index(fields=['current_period_end']),
        ]
    
    def __str__(self):
        return f"{self.school.name} - {self.plan.name} ({self.status})"
    
    def clean(self):
        """Validate subscription data."""
        from django.core.exceptions import ValidationError
        
        # Validate period dates
        if self.current_period_end and self.current_period_start:
            if self.current_period_end <= self.current_period_start:
                raise ValidationError({
                    'current_period_end': 'Period end must be after period start.'
                })
        
        # Validate plan is active
        if not self.plan.is_active:
            raise ValidationError({
                'plan': 'Selected plan is not active.'
            })
    
    def save(self, *args, **kwargs):
        """Save subscription with auto-calculated period end."""
        self.full_clean()
        
        # Set period end if not provided
        if not self.current_period_end:
            if self.billing_period == 'yearly':
                self.current_period_end = self.current_period_start + timezone.timedelta(days=365)
            else:
                self.current_period_end = self.current_period_start + timezone.timedelta(days=30)
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        """Check if subscription is currently active."""
        return self.status == StatusChoices.ACTIVE and self.current_period_end > timezone.now()
    
    @property
    def days_remaining(self):
        """Calculate days remaining in subscription."""
        if self.current_period_end > timezone.now():
            return (self.current_period_end - timezone.now()).days
        return 0
    
    @property
    def has_expired(self):
        """Check if subscription has expired."""
        return self.current_period_end <= timezone.now() 