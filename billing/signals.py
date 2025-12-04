# billing/signals.py
import logging
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import Invoice, Transaction, SchoolSubscription, FeeStructure
from students.models import Student
from admissions.models import Application, Admission
from .services import BillingService, PaystackService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Invoice)
def handle_invoice_status_change(sender, instance, created, **kwargs):
    """Handle invoice status changes and trigger appropriate actions."""
    if not created:
        try:
            # Log status changes
            old_status = Invoice.objects.get(pk=instance.pk).status
            if old_status != instance.status:
                logger.info(f"Invoice {instance.invoice_number} status changed: {old_status} -> {instance.status}")
                
                # Send notifications for overdue invoices
                if instance.status == 'overdue':
                    # In production, send email/SMS notification to parent
                    logger.info(f"Invoice {instance.invoice_number} is now overdue")
                    
                # Handle paid invoices
                elif instance.status == 'paid':
                    # Update student status if it's an acceptance fee
                    if instance.invoice_type == 'acceptance' and instance.student:
                        instance.student.admission_status = 'enrolled'
                        instance.student.save()
                        logger.info(f"Student {instance.student.full_name} enrolled after acceptance fee payment")
        
        except Invoice.DoesNotExist:
            pass  # New invoice


@receiver(post_save, sender=Transaction)
def handle_transaction_completion(sender, instance, created, **kwargs):
    """Handle transaction completion and update related models."""
    if not created and instance.status == 'success':
        try:
            # Update invoice status
            invoice = instance.invoice
            if invoice.status != 'paid':
                invoice.status = 'paid'
                invoice.paid_date = timezone.now().date()
                invoice.save()
                
                logger.info(f"Invoice {invoice.invoice_number} marked as paid via transaction {instance.paystack_reference}")
            
            # Handle application fee payments
            if invoice.invoice_type == 'application' and hasattr(invoice, 'application_fee_invoice'):
                application = invoice.application_fee_invoice
                application.application_fee_paid = True
                application.save()
                logger.info(f"Application {application.application_number} fee paid")
            
            # Handle acceptance fee payments
            if invoice.invoice_type == 'acceptance' and hasattr(invoice, 'acceptance_fee_invoice'):
                admission = invoice.acceptance_fee_invoice
                admission.acceptance_fee_paid = True
                admission.accepted = True
                admission.accepted_at = timezone.now()
                admission.save()
                logger.info(f"Admission {admission.admission_number} acceptance fee paid")
                
        except Exception as e:
            logger.error(f"Error handling transaction completion: {str(e)}")


@receiver(post_save, sender=Application)
def handle_application_submission(sender, instance, created, **kwargs):
    """Handle new application submissions."""
    if created:
        try:
            # Create application fee invoice if required
            if not instance.form.is_free and instance.form.application_fee > 0:
                invoice = BillingService.create_application_invoice(instance)
                if invoice:
                    logger.info(f"Application fee invoice created: {invoice.invoice_number}")
            
            # Send confirmation email (to be implemented)
            logger.info(f"New application submitted: {instance.application_number}")
            
        except Exception as e:
            logger.error(f"Error handling application submission: {str(e)}")


@receiver(post_save, sender=Admission)
def handle_admission_offer(sender, instance, created, **kwargs):
    """Handle new admission offers."""
    if created and instance.requires_acceptance_fee:
        try:
            # Create acceptance fee invoice
            from billing.services import BillingService
            invoice = BillingService.create_acceptance_invoice(instance)
            if invoice:
                logger.info(f"Acceptance fee invoice created: {invoice.invoice_number}")
                
        except Exception as e:
            logger.error(f"Error creating acceptance fee invoice: {str(e)}")


@receiver(pre_save, sender=SchoolSubscription)
def handle_subscription_expiry(sender, instance, **kwargs):
    """Handle subscription expiry and renewal reminders."""
    try:
        if instance.pk:
            old_instance = SchoolSubscription.objects.get(pk=instance.pk)
            
            # Check if subscription is about to expire (7 days warning)
            if (instance.current_period_end <= timezone.now() + timedelta(days=7) and 
                not instance.payment_reminder_sent and instance.status == 'active'):
                
                # Send renewal reminder (to be implemented)
                logger.info(f"Subscription renewal reminder for {instance.school.name}")
                instance.payment_reminder_sent = True
                
            # Handle expired subscriptions
            if (instance.current_period_end <= timezone.now() and 
                instance.status == 'active'):
                
                instance.status = 'expired'
                logger.warning(f"Subscription expired for {instance.school.name}")
                
    except SchoolSubscription.DoesNotExist:
        pass  # New subscription


@receiver(post_save, sender=Student)
def handle_student_enrollment(sender, instance, created, **kwargs):
    """Handle student enrollment and create initial school fees invoice."""
    if created and instance.admission_status == 'enrolled':
        try:
            # Get current academic term
            from students.models import AcademicTerm
            current_term = AcademicTerm.objects.filter(
                school=instance.school,
                is_active=True
            ).first()
            
            if current_term:
                # Get applicable fee structures
                fee_structures = FeeStructure.objects.filter(
                    school=instance.school,
                    is_active=True,
                    applicable_levels__contains=[instance.education_level.level]
                )
                
                if fee_structures.exists():
                    # Create school fees invoice
                    invoice = BillingService.create_school_fees_invoice(
                        instance, current_term, fee_structures
                    )
                    if invoice:
                        logger.info(f"School fees invoice created for {instance.full_name}: {invoice.invoice_number}")
                        
        except Exception as e:
            logger.error(f"Error creating school fees invoice for {instance.full_name}: {str(e)}")


@receiver(pre_save, sender=FeeStructure)
def validate_fee_structure(sender, instance, **kwargs):
    """Validate fee structure before saving."""
    if instance.amount < 0:
        raise ValueError("Fee amount cannot be negative")
    
    if instance.tax_rate < 0 or instance.tax_rate > 100:
        raise ValueError("Tax rate must be between 0 and 100")


# Invoice automation signals
@receiver(post_save, sender=Invoice)
def check_overdue_invoices(sender, instance, **kwargs):
    """Check and update overdue invoices."""
    if instance.due_date < timezone.now().date() and instance.status == 'sent':
        instance.status = 'overdue'
        instance.save()
        logger.info(f"Invoice {instance.invoice_number} marked as overdue")


# Connect signals
def ready():
    """Connect all signals when app is ready."""
    # These are automatically connected via @receiver decorators
    pass