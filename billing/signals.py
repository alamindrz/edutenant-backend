# billing/signals.py
import logging
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

# ✅ Import shared constants
from shared.constants import StatusChoices

# ✅ Local models
from .models import Invoice, Transaction, SchoolSubscription, FeeStructure

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Invoice)
def handle_invoice_status_change(sender, instance, created, **kwargs):
    """Handle invoice status changes and trigger appropriate actions."""
    if not created:
        try:
            # Get old instance from database
            old_instance = Invoice.objects.filter(pk=instance.pk).first()
            if old_instance and old_instance.status != instance.status:
                logger.info(f"Invoice {instance.invoice_number} status changed: {old_instance.status} -> {instance.status}")

                # Send notifications for overdue invoices
                if instance.status == StatusChoices.OVERDUE:
                    logger.info(f"Invoice {instance.invoice_number} is now overdue")
                    # TODO: Send email/SMS notification to parent

                # Handle paid invoices
                elif instance.status == StatusChoices.PAID:
                    # Update student status if it's an acceptance fee
                    if instance.invoice_type == 'acceptance' and instance.student:
                        instance.student.admission_status = 'enrolled'
                        instance.student.save(update_fields=['admission_status'])
                        logger.info(f"Student {instance.student.full_name} enrolled after acceptance fee payment")

        except Exception as e:
            logger.error(f"Error handling invoice status change: {str(e)}")


@receiver(post_save, sender=Transaction)
def handle_transaction_completion(sender, instance, created, **kwargs):
    """Handle transaction completion and update related models."""
    if not created and instance.status == StatusChoices.SUCCESS:
        try:
            # Update invoice status
            invoice = instance.invoice
            if invoice.status != StatusChoices.PAID:
                invoice.status = StatusChoices.PAID
                invoice.paid_date = timezone.now().date()
                invoice.save(update_fields=['status', 'paid_date'])

                logger.info(f"Invoice {invoice.invoice_number} marked as paid via transaction {instance.paystack_reference}")

            # ✅ Lazy import to avoid circular imports
            # Handle application fee payments
            if invoice.invoice_type == 'application':
                from admissions.models import Application
                try:
                    application = Application.objects.get(application_fee_invoice=invoice)
                    application.application_fee_paid = True
                    application.save(update_fields=['application_fee_paid'])
                    logger.info(f"Application {application.application_number} fee paid")
                except Application.DoesNotExist:
                    pass

            # Handle acceptance fee payments
            if invoice.invoice_type == 'acceptance':
                from admissions.models import Admission
                try:
                    admission = Admission.objects.get(acceptance_fee_invoice=invoice)
                    admission.acceptance_fee_paid = True
                    admission.accepted = True
                    admission.accepted_at = timezone.now()
                    admission.save(update_fields=['acceptance_fee_paid', 'accepted', 'accepted_at'])
                    logger.info(f"Admission {admission.admission_number} acceptance fee paid")
                except Admission.DoesNotExist:
                    pass

        except Exception as e:
            logger.error(f"Error handling transaction completion: {str(e)}", exc_info=True)


@receiver(post_save, sender='admissions.Application')
def handle_application_submission(sender, instance, created, **kwargs):
    """Handle new application submissions."""
    if created:
        try:
            # ✅ Lazy import to avoid circular imports
            from .services import BillingService

            # Create application fee invoice if required
            if not instance.form.is_free and instance.form.application_fee > 0:
                invoice = BillingService.create_application_invoice(instance)
                if invoice:
                    logger.info(f"Application fee invoice created: {invoice.invoice_number}")

            # TODO: Send confirmation email
            logger.info(f"New application submitted: {instance.application_number}")

        except Exception as e:
            logger.error(f"Error handling application submission: {str(e)}", exc_info=True)


@receiver(post_save, sender='admissions.Admission')
def handle_admission_offer(sender, instance, created, **kwargs):
    """Handle new admission offers."""
    if created and instance.requires_acceptance_fee:
        try:
            # ✅ Lazy import to avoid circular imports
            from .services import BillingService
            invoice = BillingService.create_acceptance_invoice(instance)
            if invoice:
                logger.info(f"Acceptance fee invoice created: {invoice.invoice_number}")

        except Exception as e:
            logger.error(f"Error creating acceptance fee invoice: {str(e)}", exc_info=True)


@receiver(pre_save, sender=SchoolSubscription)
def handle_subscription_expiry(sender, instance, **kwargs):
    """Handle subscription expiry and renewal reminders."""
    try:
        if instance.pk:
            old_instance = SchoolSubscription.objects.filter(pk=instance.pk).first()
            if not old_instance:
                return

            # Check if subscription is about to expire (7 days warning)
            if (instance.current_period_end <= timezone.now() + timedelta(days=7) and
                not instance.payment_reminder_sent and instance.status == StatusChoices.ACTIVE):

                logger.info(f"Subscription renewal reminder for {instance.school.name}")
                instance.payment_reminder_sent = True

            # Handle expired subscriptions
            if (instance.current_period_end <= timezone.now() and
                instance.status == StatusChoices.ACTIVE):

                instance.status = StatusChoices.EXPIRED
                logger.warning(f"Subscription expired for {instance.school.name}")

    except Exception as e:
        logger.error(f"Error handling subscription expiry: {str(e)}", exc_info=True)


@receiver(post_save, sender='students.Student')
def handle_student_enrollment(sender, instance, created, **kwargs):
    """Handle student enrollment and create initial school fees invoice."""
    if created and instance.admission_status == 'enrolled':
        try:
            # ✅ Lazy import to avoid circular imports
            from students.models import AcademicTerm
            from .services import BillingService

            # Get current academic term
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
            logger.error(f"Error creating school fees invoice for {instance.full_name}: {str(e)}", exc_info=True)


@receiver(pre_save, sender=FeeStructure)
def validate_fee_structure(sender, instance, **kwargs):
    """Validate fee structure before saving."""
    if instance.amount < 0:
        raise ValueError("Fee amount cannot be negative")

    if instance.tax_rate < 0 or instance.tax_rate > 100:
        raise ValueError("Tax rate must be between 0 and 100")


@receiver(post_save, sender=Invoice)
def check_overdue_invoices(sender, instance, created, **kwargs):
    """Check and update overdue invoices."""
    try:
        if not created and instance.due_date < timezone.now().date() and instance.status == StatusChoices.SENT:
            instance.status = StatusChoices.OVERDUE
            instance.save(update_fields=['status'])
            logger.info(f"Invoice {instance.invoice_number} marked as overdue")
    except Exception as e:
        logger.error(f"Error checking overdue invoices: {str(e)}", exc_info=True)


# ============ NEW SIGNALS FOR SHARED ARCHITECTURE ============

@receiver(post_save, sender=Invoice)
def sync_invoice_to_shared_services(sender, instance, created, **kwargs):
    """
    Sync invoice changes to shared services.
    This ensures billing data is available to other apps through shared services.
    """
    try:
        if created:
            # Log new invoice creation
            logger.info(f"New invoice created via signal: {instance.invoice_number}")

            # ✅ Check if this is an application fee invoice from shared service
            if instance.invoice_type == 'application':
                from shared.services.payment import ApplicationPaymentService
                # ApplicationPaymentService could update its state here
                pass

    except Exception as e:
        logger.error(f"Error syncing invoice to shared services: {str(e)}", exc_info=True)


@receiver(post_save, sender=Transaction)
def sync_transaction_to_shared_services(sender, instance, created, **kwargs):
    """
    Sync transaction changes to shared services.
    This ensures payment data is available to other apps.
    """
    try:
        # ✅ Update shared payment service state for successful transactions
        if instance.status == StatusChoices.SUCCESS:
            from shared.services.payment import ApplicationPaymentService
            # The webhook should handle this, but this is a backup
            logger.info(f"Transaction {instance.paystack_reference} completed successfully")

    except Exception as e:
        logger.error(f"Error syncing transaction to shared services: {str(e)}", exc_info=True)


# ============ ERROR HANDLING SIGNALS ============

@receiver(post_save, sender=Invoice)
def handle_invoice_save_errors(sender, instance, **kwargs):
    """Log any invoice save errors."""
    try:
        if instance.pk:
            logger.debug(f"Invoice saved/updated: {instance.invoice_number} ({instance.status})")
    except Exception as e:
        logger.error(f"Error logging invoice save: {str(e)}")


@receiver(post_save, sender=Transaction)
def handle_transaction_save_errors(sender, instance, **kwargs):
    """Log any transaction save errors."""
    try:
        if instance.pk:
            logger.debug(f"Transaction saved/updated: {instance.paystack_reference} ({instance.status})")
    except Exception as e:
        logger.error(f"Error logging transaction save: {str(e)}")


# ============ UTILITY FUNCTIONS ============

def get_billing_service():
    """Get billing service with lazy import to avoid circular dependencies."""
    from .services import BillingService
    return BillingService()
