# billing/signals.py
import logging
from datetime import timedelta

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from shared.constants import StatusChoices
from .models import Invoice, Transaction, SchoolSubscription, FeeStructure

logger = logging.getLogger(__name__)


# ============================================================
# INVOICE STATUS CHANGE (FIXED – uses pre_save)
# ============================================================

@receiver(pre_save, sender=Invoice)
def handle_invoice_status_change(sender, instance, **kwargs):
    """
    Detect invoice status changes correctly.
    pre_save is required to access previous DB values.
    """
    if not instance.pk:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old_instance.status == instance.status:
        return

    logger.info(
        f"Invoice {instance.invoice_number} status changed: "
        f"{old_instance.status} -> {instance.status}"
    )

    # Overdue notification
    if instance.status == StatusChoices.OVERDUE:
        logger.info(f"Invoice {instance.invoice_number} is now overdue")
        # TODO: notify parent

    # Paid invoice handling
    if instance.status == StatusChoices.PAID:
        if instance.invoice_type == 'acceptance' and instance.student:
            instance.student.admission_status = 'enrolled'
            instance.student.save(update_fields=['admission_status'])
            logger.info(
                f"Student {instance.student.full_name} enrolled "
                f"after acceptance fee payment"
            )


# ============================================================
# TRANSACTION COMPLETION
# ============================================================

@receiver(post_save, sender=Transaction)
def handle_transaction_completion(sender, instance, created, **kwargs):
    if created or instance.status != StatusChoices.SUCCESS:
        return

    try:
        invoice = instance.invoice

        # Prevent recursive updates
        if invoice.status != StatusChoices.PAID:
            invoice.status = StatusChoices.PAID
            invoice.paid_date = timezone.now().date()
            invoice.save(update_fields=['status', 'paid_date'])

            logger.info(
                f"Invoice {invoice.invoice_number} marked as paid "
                f"via transaction {instance.paystack_reference}"
            )

        # Lazy imports (avoid circular deps)
        if invoice.invoice_type == 'application':
            from admissions.models import Application
            try:
                app = Application.objects.get(application_fee_invoice=invoice)
                app.application_fee_paid = True
                app.save(update_fields=['application_fee_paid'])
            except Application.DoesNotExist:
                pass

        if invoice.invoice_type == 'acceptance':
            from admissions.models import Admission
            try:
                admission = Admission.objects.get(acceptance_fee_invoice=invoice)
                admission.acceptance_fee_paid = True
                admission.accepted = True
                admission.accepted_at = timezone.now()
                admission.save(
                    update_fields=[
                        'acceptance_fee_paid',
                        'accepted',
                        'accepted_at',
                    ]
                )
            except Admission.DoesNotExist:
                pass

    except Exception as e:
        logger.error(
            "Error handling transaction completion",
            exc_info=True,
        )


# ============================================================
# APPLICATION SUBMISSION
# ============================================================

@receiver(post_save, sender='admissions.Application')
def handle_application_submission(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        from .services import BillingService

        if not instance.form.is_free and instance.form.application_fee > 0:
            invoice = BillingService.create_application_invoice(instance)
            if invoice:
                logger.info(
                    f"Application fee invoice created: {invoice.invoice_number}"
                )

        logger.info(
            f"New application submitted: {instance.application_number}"
        )

    except Exception:
        logger.error(
            "Error handling application submission",
            exc_info=True,
        )


# ============================================================
# ADMISSION OFFER
# ============================================================

@receiver(post_save, sender='admissions.Admission')
def handle_admission_offer(sender, instance, created, **kwargs):
    if not created or not instance.requires_acceptance_fee:
        return

    try:
        from .services import BillingService
        invoice = BillingService.create_acceptance_invoice(instance)
        if invoice:
            logger.info(
                f"Acceptance fee invoice created: {invoice.invoice_number}"
            )
    except Exception:
        logger.error(
            "Error creating acceptance fee invoice",
            exc_info=True,
        )


# ============================================================
# SCHOOL SUBSCRIPTION EXPIRY
# ============================================================

@receiver(pre_save, sender=SchoolSubscription)
def handle_subscription_expiry(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old = sender.objects.get(pk=instance.pk)

        now = timezone.now()

        # Renewal reminder
        if (
            instance.current_period_end <= now + timedelta(days=7)
            and not old.payment_reminder_sent
            and instance.status == StatusChoices.ACTIVE
        ):
            instance.payment_reminder_sent = True
            logger.info(
                f"Subscription renewal reminder for {instance.school.name}"
            )

        # Expiration
        if (
            instance.current_period_end <= now
            and old.status == StatusChoices.ACTIVE
        ):
            instance.status = StatusChoices.EXPIRED
            logger.warning(
                f"Subscription expired for {instance.school.name}"
            )

    except SchoolSubscription.DoesNotExist:
        pass
    except Exception:
        logger.error(
            "Error handling subscription expiry",
            exc_info=True,
        )


# ============================================================
# STUDENT ENROLLMENT → SCHOOL FEES INVOICE
# ============================================================

@receiver(post_save, sender='students.Student')
def handle_student_enrollment(sender, instance, created, **kwargs):
    if not created or instance.admission_status != 'enrolled':
        return

    try:
        from students.models import AcademicTerm
        from .services import BillingService

        term = AcademicTerm.objects.filter(
            school=instance.school,
            is_active=True,
        ).first()

        if not term:
            return

        fees = FeeStructure.objects.filter(
            school=instance.school,
            is_active=True,
            applicable_levels__contains=[instance.education_level.level],
        )

        if fees.exists():
            invoice = BillingService.create_school_fees_invoice(
                instance,
                term,
                fees,
            )
            if invoice:
                logger.info(
                    f"School fees invoice created for "
                    f"{instance.full_name}: {invoice.invoice_number}"
                )

    except Exception:
        logger.error(
            "Error creating school fees invoice",
            exc_info=True,
        )


# ============================================================
# FEE STRUCTURE VALIDATION
# ============================================================

@receiver(pre_save, sender=FeeStructure)
def validate_fee_structure(sender, instance, **kwargs):
    if instance.amount < 0:
        raise ValueError("Fee amount cannot be negative")

    if not 0 <= instance.tax_rate <= 100:
        raise ValueError("Tax rate must be between 0 and 100")


# ============================================================
# OVERDUE INVOICE CHECK (SAFE)
# ============================================================

@receiver(pre_save, sender=Invoice)
def mark_invoice_overdue(sender, instance, **kwargs):
    if not instance.pk:
        return

    if (
        instance.status == StatusChoices.SENT
        and instance.due_date < timezone.now().date()
    ):
        instance.status = StatusChoices.OVERDUE


# ============================================================
# SHARED SERVICE SYNC
# ============================================================

@receiver(post_save, sender=Invoice)
def sync_invoice_to_shared_services(sender, instance, created, **kwargs):
    try:
        if created:
            logger.info(
                f"New invoice created via signal: {instance.invoice_number}"
            )
    except Exception:
        logger.error(
            "Error syncing invoice to shared services",
            exc_info=True,
        )


@receiver(post_save, sender=Transaction)
def sync_transaction_to_shared_services(sender, instance, **kwargs):
    try:
        if instance.status == StatusChoices.SUCCESS:
            logger.info(
                f"Transaction {instance.paystack_reference} completed successfully"
            )
    except Exception:
        logger.error(
            "Error syncing transaction to shared services",
            exc_info=True,
        )

@receiver(post_save, sender=Invoice)
def check_overdue_invoices(sender, instance, created, **kwargs):
    """
    Mark invoices as overdue without triggering recursive signals.
    """
    if created:
        return

    if (
        instance.status == StatusChoices.SENT
        and instance.due_date < timezone.now().date()
    ):
        Invoice.objects.filter(
            pk=instance.pk,
            status=StatusChoices.SENT,
        ).update(status=StatusChoices.OVERDUE)

        logger.info(
            f"Invoice {instance.invoice_number} marked as overdue"
        )


# ============================================================
# DEBUG LOGGING (SAFE, NON-RECURSIVE)
# ============================================================


@receiver(pre_save, sender=Invoice)
def mark_invoice_overdue(sender, instance, **kwargs):
    if (
        instance.pk
        and instance.status == StatusChoices.SENT
        and instance.due_date < timezone.now().date()
    ):
        instance.status = StatusChoices.OVERDUE


@receiver(post_save, sender=Invoice)
def log_invoice_save(sender, instance, **kwargs):
    logger.debug(
        f"Invoice saved: {instance.invoice_number} ({instance.status})"
    )
    
    
@receiver(post_save, sender=Transaction)
def log_transaction_save(sender, instance, **kwargs):
    logger.debug(
        f"Transaction saved: "
        f"{instance.paystack_reference} ({instance.status})"
    )