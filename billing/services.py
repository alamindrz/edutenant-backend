# billing/services.py
"""
CLEAN Billing Services - Using shared architecture.
NO duplicate services - imports everything from shared.
"""
import logging
import uuid
import json
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta

# SHARED IMPORTS - SINGLE SOURCE OF TRUTH
from shared.services.payment.payment_core import PaymentCoreService
from shared.services.payment.paystack import PaystackService
from shared.services.payment.application_fee import ApplicationPaymentService
from shared.utils import IdempotencyService
from shared.exceptions.payment import PaymentProcessingError

# LOCAL MODELS ONLY
from .models import Invoice, Transaction, InvoiceItem, FeeStructure, SubdomainPlan, SchoolSubscription

logger = logging.getLogger(__name__)


# ============ IDEMPOTENCY SERVICE ============
# NOTE: Moved to shared/utils/idempotency.py
# Using shared.IdempotencyService instead


# ============ PAYSTACK SERVICE ============
# NOTE: Moved to shared/services/payment/paystack.py
# Using shared.services.payment.PaystackService instead


# ============ PAYMENT SERVICE (LOCAL - Billing Specific) ============

class BillingPaymentService:
    """
    Billing-specific payment service.
    Handles invoice-specific logic while using shared payment services.
    """
    
    @staticmethod
    @transaction.atomic
    def create_invoice_payment(invoice, customer_email, metadata=None):
        """
        Create payment for an invoice using shared PaystackService.
        
        Args:
            invoice: Invoice instance
            customer_email: Customer email for Paystack
            metadata: Additional metadata for Paystack
            
        Returns:
            dict: Payment data from Paystack
        """
        try:
            # Use shared PaystackService
            paystack_service = PaystackService()
            
            # Prepare metadata
            payment_metadata = {
                'invoice_id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'school_id': invoice.school.id,
                'parent_id': invoice.parent.id,
                'student_id': invoice.student.id if invoice.student else None,
                'invoice_type': invoice.invoice_type,
            }
            
            if metadata:
                payment_metadata.update(metadata)
            
            # Initialize payment
            payment_data = paystack_service.initialize_payment(
                invoice=invoice,
                customer_email=customer_email,
                metadata=payment_metadata
            )
            
            # Create transaction record
            transaction = Transaction.objects.create(
                invoice=invoice,
                paystack_reference=payment_data['reference'],
                amount=invoice.total_amount,
                platform_fee=invoice.platform_fee,
                paystack_fee=invoice.paystack_fee,
                school_amount=invoice.total_amount - invoice.platform_fee - invoice.paystack_fee,
                status='pending',
                metadata=payment_metadata,
                channel='web'  # Will be updated by webhook
            )
            
            logger.info(f"Invoice payment initialized: {invoice.invoice_number}, Ref: {payment_data['reference']}")
            
            return payment_data
            
        except PaymentProcessingError as e:
            logger.error(f"Payment initialization failed for invoice {invoice.id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating invoice payment: {str(e)}", exc_info=True)
            raise PaymentProcessingError(
                "Failed to initialize payment. Please try again.",
                user_friendly=True
            )
    
    @staticmethod
    @transaction.atomic
    def process_payment_webhook(webhook_data, webhook_signature=None):
        """
        Process payment webhook for billing invoices.
        Uses shared idempotency service.
        
        Args:
            webhook_data: Dict from Paystack webhook
            webhook_signature: Webhook signature for verification
            
        Returns:
            bool: True if processed successfully
        """
        webhook_id = webhook_data.get('id', str(uuid.uuid4()))
        event = webhook_data.get('event')
        
        # Verify webhook signature using shared PaystackService
        if webhook_signature:
            paystack_service = PaystackService()
            if not paystack_service.verify_webhook_signature(
                json.dumps(webhook_data).encode('utf-8'),
                webhook_signature
            ):
                logger.error(f"[{webhook_id}] Invalid webhook signature")
                return False
        
        # Check idempotency using shared service
        idempotency_key = IdempotencyService.get_key('webhook', webhook_id)
        if not IdempotencyService.check_and_lock(idempotency_key):
            logger.info(f"[{webhook_id}] Webhook already processed or being processed")
            return True  # Return success for idempotent duplicates
        
        try:
            data = webhook_data['data']
            
            if event == 'charge.success':
                success = BillingPaymentService._handle_successful_charge(data, webhook_id)
            elif event == 'charge.failed':
                success = BillingPaymentService._handle_failed_charge(data, webhook_id)
            elif event == 'transfer.success':
                success = BillingPaymentService._handle_transfer_success(data, webhook_id)
            else:
                logger.info(f"[{webhook_id}] Unhandled event: {event}")
                success = True  # Success for valid but unhandled events
            
            if success:
                IdempotencyService.mark_processed(idempotency_key)
            else:
                IdempotencyService.mark_failed(idempotency_key)
            
            return success
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Webhook processing error: {e}", exc_info=True)
            IdempotencyService.mark_failed(idempotency_key)
            raise  # Re-raise to trigger transaction rollback
    
    @staticmethod
    def _handle_successful_charge(data, webhook_id):
        """Handle successful charge webhook for invoices."""
        try:
            reference = data.get('reference')
            if not reference:
                logger.error(f"[{webhook_id}] No reference in webhook")
                return False
            
            # Find transaction
            transaction = Transaction.objects.select_related('invoice').get(
                paystack_reference=reference
            )
            
            # Prevent duplicate processing
            if transaction.status == 'success':
                logger.info(f"[{webhook_id}] Transaction already processed: {reference}")
                return True
            
            # Calculate amounts
            amount = Decimal(str(data.get('amount', 0))) / 100
            fees = Decimal(str(data.get('fees', 0))) / 100
            
            # Update transaction
            transaction.status = 'success'
            transaction.completed_at = timezone.now()
            transaction.paystack_response = data
            transaction.channel = data.get('channel', '')
            
            # Calculate school amount (amount - platform_fee - paystack_fee)
            # Note: fees from Paystack might be different from our estimates
            actual_paystack_fee = fees
            transaction.paystack_fee = actual_paystack_fee
            transaction.school_amount = amount - transaction.platform_fee - actual_paystack_fee
            
            if transaction.school_amount < 0:
                logger.warning(f"[{webhook_id}] Negative school amount: {transaction.school_amount}")
                transaction.school_amount = Decimal('0')
            
            transaction.save()
            
            # Update invoice
            invoice = transaction.invoice
            invoice.status = 'paid'
            invoice.paid_date = timezone.now().date()
            invoice.paystack_reference = reference
            invoice.save()
            
            logger.info(f"[{webhook_id}] Invoice payment processed: {reference} for invoice {invoice.invoice_number}")
            
            # Trigger invoice-specific post-payment actions
            BillingPaymentService._trigger_invoice_post_payment_actions(invoice, webhook_id)
            
            return True
            
        except Transaction.DoesNotExist:
            logger.error(f"[{webhook_id}] Transaction not found: {reference}")
            
            # Try to find invoice by metadata and create transaction
            return BillingPaymentService._handle_orphaned_charge(data, webhook_id)
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Error processing charge: {e}")
            return False
    
    @staticmethod
    def _handle_orphaned_charge(data, webhook_id):
        """
        Handle charge where transaction doesn't exist but invoice does.
        This can happen if webhook arrives before transaction is created.
        """
        try:
            reference = data.get('reference')
            metadata = data.get('metadata', {})
            invoice_id = metadata.get('invoice_id')
            
            if not invoice_id:
                logger.error(f"[{webhook_id}] No invoice_id in metadata for orphaned charge")
                return False
            
            # Find invoice
            invoice = Invoice.objects.get(id=invoice_id)
            
            # Create transaction
            amount = Decimal(str(data.get('amount', 0))) / 100
            fees = Decimal(str(data.get('fees', 0))) / 100
            
            transaction = Transaction.objects.create(
                invoice=invoice,
                paystack_reference=reference,
                amount=amount,
                platform_fee=invoice.platform_fee,
                paystack_fee=fees,
                school_amount=amount - invoice.platform_fee - fees,
                status='success',
                completed_at=timezone.now(),
                paystack_response=data,
                channel=data.get('channel', ''),
                metadata=metadata
            )
            
            # Update invoice
            invoice.status = 'paid'
            invoice.paid_date = timezone.now().date()
            invoice.paystack_reference = reference
            invoice.save()
            
            logger.info(f"[{webhook_id}] Orphaned charge handled, created transaction: {transaction.id}")
            return True
            
        except Invoice.DoesNotExist:
            logger.error(f"[{webhook_id}] Invoice not found: {invoice_id}")
            return False
        except Exception as e:
            logger.error(f"[{webhook_id}] Error handling orphaned charge: {e}")
            return False
    
    @staticmethod
    def _handle_failed_charge(data, webhook_id):
        """Handle failed charge webhook."""
        try:
            reference = data.get('reference')
            if not reference:
                logger.error(f"[{webhook_id}] No reference in failed charge")
                return False
            
            # Find transaction
            transaction = Transaction.objects.filter(paystack_reference=reference).first()
            
            if transaction:
                transaction.status = 'failed'
                transaction.completed_at = timezone.now()
                transaction.paystack_response = data
                transaction.save()
                
                logger.info(f"[{webhook_id}] Transaction marked as failed: {reference}")
            else:
                logger.warning(f"[{webhook_id}] Failed charge transaction not found: {reference}")
            
            return True
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Error processing failed charge: {e}")
            return False
    
    @staticmethod
    def _handle_transfer_success(data, webhook_id):
        """Handle successful transfer webhook (payouts to schools)."""
        try:
            reference = data.get('reference')
            amount = Decimal(str(data.get('amount', 0))) / 100
            
            logger.info(f"[{webhook_id}] Transfer successful: {reference} - ₦{amount:,.2f}")
            
            # In a real implementation, you would:
            # 1. Update school balance
            # 2. Create payout record
            # 3. Send notification to school
            
            return True
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Error processing transfer: {e}")
            return False
    
    @staticmethod
    def _trigger_invoice_post_payment_actions(invoice, webhook_id):
        """Trigger invoice-specific actions after successful payment."""
        try:
            # Import here to avoid circular imports
            if invoice.invoice_type == 'application_fee':
                # This should be handled by ApplicationPaymentService
                # Log for debugging
                logger.info(f"[{webhook_id}] Application fee paid: {invoice.invoice_number}")
                
            elif invoice.invoice_type == 'acceptance_fee':
                # Handle acceptance fee payment
                from admissions.models import Admission
                
                admission = Admission.objects.filter(
                    acceptance_fee_invoice=invoice
                ).first()
                
                if admission:
                    admission.acceptance_fee_paid = True
                    admission.save()
                    logger.info(f"[{webhook_id}] Acceptance fee marked as paid for admission: {admission.id}")
            
            elif invoice.invoice_type == 'school_fees':
                # Handle tuition fee payment
                # This could trigger enrollment confirmation, update student status, etc.
                logger.info(f"[{webhook_id}] School fees paid: {invoice.invoice_number}")
                
                # Update student's fee payment status if needed
                if invoice.student:
                    # Add logic to update student fee records
                    pass
            
            # Send payment confirmation email
            BillingPaymentService._send_payment_confirmation_email(invoice, webhook_id)
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Post-payment action error: {e}")
            # Don't fail the webhook for post-payment errors
    
    @staticmethod
    def _send_payment_confirmation_email(invoice, webhook_id):
        """Send payment confirmation email."""
        try:
            # This would integrate with your email service
            # For now, just log
            
            email_data = {
                'to': invoice.parent.email,
                'subject': f"Payment Confirmation - Invoice {invoice.invoice_number}",
                'invoice': invoice,
                'amount': invoice.total_amount,
                'date': timezone.now().strftime('%B %d, %Y'),
            }
            
            logger.info(f"[{webhook_id}] Would send payment confirmation email: {email_data}")
            
            # Example:
            # email_service.send_template(
            #     template='payment_confirmation.html',
            #     context=email_data
            # )
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Failed to send payment email: {e}")


# ============ APPLICATION PAYMENT SERVICE ============
# NOTE: Moved to shared/services/payment/application_fee.py
# Using shared.services.payment.ApplicationPaymentService instead


# ============ FEE STRUCTURE SERVICE (LOCAL) ============

class FeeStructureService:
    """Service for managing fee structures."""
    
    @staticmethod
    def generate_invoice_from_fee_structure(student, term, fee_structures=None):
        """
        Generate invoice for student based on fee structures.
        
        Args:
            student: Student instance
            term: AcademicTerm instance
            fee_structures: Optional list of specific fee structures
            
        Returns:
            Invoice: Generated invoice
        """
        try:
            if not fee_structures:
                # Get applicable fee structures for student
                fee_structures = FeeStructure.objects.filter(
                    school=student.school,
                    is_active=True,
                    applicable_levels__contains=[student.current_class.level] if student.current_class else []
                )
            
            if not fee_structures.exists():
                raise ValidationError("No applicable fee structures found for student.")
            
            # Calculate totals
            subtotal = Decimal('0')
            items_data = []
            
            for fee_structure in fee_structures:
                amount = fee_structure.amount
                subtotal += amount
                
                items_data.append({
                    'fee_structure': fee_structure,
                    'description': fee_structure.name,
                    'quantity': 1,
                    'unit_price': amount,
                    'amount': amount,
                })
            
            # Calculate platform and Paystack fees
            platform_fee = subtotal * Decimal('0.015')  # 1.5%
            paystack_fee = subtotal * Decimal('0.015')  # 1.5%
            tax_amount = subtotal * (fee_structures.first().tax_rate / Decimal('100')) if fee_structures.exists() else Decimal('0')
            
            total_amount = subtotal + platform_fee + paystack_fee + tax_amount
            
            # Create invoice
            invoice = Invoice.objects.create(
                school=student.school,
                parent=student.parent,
                student=student,
                invoice_type='school_fees',
                subtotal=subtotal,
                platform_fee=platform_fee,
                paystack_fee=paystack_fee,
                discount=Decimal('0'),
                tax_amount=tax_amount,
                total_amount=total_amount,
                status='draft',
                due_date=term.end_date or timezone.now().date() + timedelta(days=30),
                term=term,
                session=term.academic_session.session if term.academic_session else '',
            )
            
            # Create invoice items
            for item_data in items_data:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    fee_structure=item_data['fee_structure'],
                    description=item_data['description'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    amount=item_data['amount'],
                )
            
            logger.info(f"Invoice generated: {invoice.invoice_number} for student {student.id}")
            return invoice
            
        except Exception as e:
            logger.error(f"Failed to generate invoice: {str(e)}", exc_info=True)
            raise ValidationError(f"Failed to generate invoice: {str(e)}")


# ============ SUBSCRIPTION SERVICE (LOCAL) ============

class SubscriptionService:
    """Service for managing school subscriptions."""
    
    @staticmethod
    def create_subscription(school, plan, billing_period='monthly'):
        """
        Create subscription for school.
        
        Args:
            school: School instance
            plan: SubdomainPlan instance
            billing_period: 'monthly' or 'yearly'
            
        Returns:
            SchoolSubscription: Created subscription
        """
        try:
            # Calculate period end
            if billing_period == 'yearly':
                period_end = timezone.now() + timedelta(days=365)
            else:
                period_end = timezone.now() + timedelta(days=30)
            
            subscription = SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                billing_period=billing_period,
                current_period_start=timezone.now(),
                current_period_end=period_end,
                status='trialing',  # Start with trial
            )
            
            logger.info(f"Subscription created for school {school.id}: {plan.name}")
            return subscription
            
        except Exception as e:
            logger.error(f"Failed to create subscription: {str(e)}")
            raise ValidationError(f"Failed to create subscription: {str(e)}")
    
    @staticmethod
    def update_subscription_status(subscription, status):
        """
        Update subscription status.
        
        Args:
            subscription: SchoolSubscription instance
            status: New status
            
        Returns:
            SchoolSubscription: Updated subscription
        """
        try:
            valid_statuses = dict(SchoolSubscription.STATUS_CHOICES).keys()
            if status not in valid_statuses:
                raise ValidationError(f"Invalid status: {status}")
            
            subscription.status = status
            subscription.save()
            
            logger.info(f"Subscription {subscription.id} status updated to {status}")
            return subscription
            
        except Exception as e:
            logger.error(f"Failed to update subscription status: {str(e)}")
            raise ValidationError(f"Failed to update subscription status: {str(e)}")


# ============ SHORTCUT FUNCTIONS FOR BACKWARD COMPATIBILITY ============

# These functions maintain backward compatibility with existing code
# They delegate to the appropriate shared services

def initialize_payment(invoice, customer_email, metadata=None):
    """Backward compatibility - delegates to BillingPaymentService."""
    return BillingPaymentService.create_invoice_payment(invoice, customer_email, metadata)

def verify_transaction(reference):
    """Backward compatibility - delegates to shared PaystackService."""
    paystack_service = PaystackService()
    return paystack_service.verify_transaction(reference)

def process_payment_webhook(webhook_data, signature=None):
    """Backward compatibility - delegates to BillingPaymentService."""
    return BillingPaymentService.process_payment_webhook(webhook_data, signature)

# Legacy class names for backward compatibility
# These will be deprecated over time
PaymentService = BillingPaymentService  # Alias for backward compatibility
ApplicationPaymentService = ApplicationPaymentService  # From shared

# Export services
__all__ = [
    'BillingPaymentService',
    'FeeStructureService',
    'SubscriptionService',
    'PaymentService',  # Legacy alias
    'ApplicationPaymentService',  # From shared
    'initialize_payment',  # Legacy function
    'verify_transaction',  # Legacy function
    'process_payment_webhook',  # Legacy function
] 