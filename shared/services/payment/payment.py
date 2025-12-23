"""
Core payment services - NO external dependencies.
Used by admissions WITHOUT circular imports.
DEPENDS ON: Django, shared.constants
"""
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from shared.constants import StatusChoices, PaymentMethods

class PaymentCoreService:
    """
    Core payment logic - NO Paystack or external API dependencies.
    Pure database operations only.
    """
    
    @staticmethod
    def create_invoice(amount, student, invoice_type, description="", due_days=7):
        """
        Create invoice with consistent field names.
        
        Args:
            amount: Decimal amount
            student: Student instance
            invoice_type: Type of invoice
            description: Invoice description
            due_days: Days until due
        
        Returns:
            Invoice instance
        """
        # Import here to avoid circular imports at module level
        from core.models import Invoice
        
        invoice = Invoice.objects.create(
            student=student,
            amount=amount,
            invoice_type=invoice_type,
            description=description,
            payment_status=StatusChoices.PENDING,
            due_date=timezone.now() + timezone.timedelta(days=due_days)
        )
        return invoice
    
    @staticmethod
    def mark_paid(invoice, payment_method=PaymentMethods.PAYSTACK, 
                  reference="", notes=""):
        """
        Mark invoice as paid and create payment record.
        
        Args:
            invoice: Invoice instance
            payment_method: Payment method
            reference: Payment reference
            notes: Additional notes
        
        Returns:
            tuple: (invoice, payment)
        """
        from core.models import Payment
        
        # Update invoice
        invoice.payment_status = StatusChoices.PAID
        invoice.paid_at = timezone.now()
        invoice.save()
        
        # Create payment record
        payment = Payment.objects.create(
            invoice=invoice,
            amount=invoice.amount,
            payment_method=payment_method,
            reference=reference,
            status=StatusChoices.COMPLETED,
            notes=notes
        )
        
        return invoice, payment
    
    @staticmethod
    def create_zero_amount_invoice(student, invoice_type, description):
        """
        Create a zero-amount invoice (for waivers or staff discounts).
        Automatically marks as paid.
        """
        from core.models import Invoice, Payment
        
        # Create zero-amount invoice
        invoice = Invoice.objects.create(
            student=student,
            amount=0,
            invoice_type=invoice_type,
            description=description,
            payment_status=StatusChoices.PAID,
            paid_at=timezone.now()
        )
        
        # Create waiver payment record
        Payment.objects.create(
            invoice=invoice,
            amount=0,
            payment_method=PaymentMethods.WAIVER,
            reference=f"WAIVER-{invoice.id}",
            status=StatusChoices.COMPLETED,
            notes="Zero amount invoice for waiver/discount"
        )
        
        return invoice
    
    @staticmethod
    def get_student_invoices(student, status=None):
        """Get all invoices for a student, optionally filtered by status."""
        from core.models import Invoice
        
        queryset = Invoice.objects.filter(student=student)
        
        if status:
            queryset = queryset.filter(payment_status=status)
        
        return queryset.order_by('-created_at') 