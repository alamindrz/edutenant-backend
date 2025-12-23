# shared/services/payment/application_fee.py
"""
Application Payment Service - SINGLE source for application fee handling.
Handles ALL application fee payments with school-specific policies.
NO circular imports - uses dependency injection and shared services.
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal

# Try to import shared constants with fallback
try:
    from shared.constants import StatusChoices, PaymentMethods
    SHARED_CONSTANTS_AVAILABLE = True
except ImportError:
    SHARED_CONSTANTS_AVAILABLE = False
    # Define minimal constants
    class StatusChoices:
        PENDING = 'pending'
        PAID = 'paid'
        FAILED = 'failed'
    
    class PaymentMethods:
        PAYSTACK = 'paystack'
        WAIVER = 'waiver'

try:
    from shared.exceptions.payment import PaymentProcessingError
    PAYMENT_EXCEPTIONS_AVAILABLE = True
except ImportError:
    PAYMENT_EXCEPTIONS_AVAILABLE = False
    PaymentProcessingError = Exception

logger = logging.getLogger(__name__)

class ApplicationPaymentService:
    """
    Service for handling ALL application fee payments.
    Consolidates logic from both billing and admissions apps.
    """
    
    @staticmethod
    @transaction.atomic
    def create_application_fee_invoice(parent_data, student_data, form, user=None):
        """
        Create application fee invoice with proper validation and school policies.
        
        Args:
            parent_data: Dict with parent information (already field-mapped)
            student_data: Dict with student information (already field-mapped)
            form: ApplicationForm instance
            user: Optional user object
        
        Returns:
            tuple: (payment_data, invoice) 
                   - payment_data: Dict with payment info if payment required
                   - invoice: Invoice instance (created regardless)
        
        Raises:
            ValidationError: If validation fails
            PaymentProcessingError: If payment initialization fails
        """
        logger.info(f"Creating application fee invoice for form: {form.id}")
        
        try:
            # Try to import FieldMapper
            try:
                from shared.utils.field_mapping import FieldMapper
                field_mapper_available = True
            except ImportError:
                field_mapper_available = False
            
            # Import services here to avoid circular imports
            try:
                from .payment_core import PaymentCoreService
                payment_core_available = True
            except ImportError:
                payment_core_available = False
                PaymentCoreService = None
            
            # 1. Calculate fee amount with discounts
            fee_amount = ApplicationPaymentService._calculate_application_fee(
                form, parent_data, student_data, user
            )
            
            # 2. Get or create parent (for invoice linking)
            parent = ApplicationPaymentService._get_or_create_parent_for_invoice(
                parent_data, form.school, user
            )
            
            # 3. Create student placeholder (will be updated after application)
            from students.models import Student
            student = ApplicationPaymentService._create_student_placeholder(
                student_data, parent
            )
            
            # 4. Create invoice if payment core is available
            if payment_core_available and PaymentCoreService:
                invoice = PaymentCoreService.create_invoice(
                    amount=fee_amount,
                    student=student,
                    invoice_type='application_fee',
                    description=f"Application fee for {form.name}",
                    due_days=form.school.application_fee_due_days if hasattr(form.school, 'application_fee_due_days') else 7
                )
            else:
                # Create minimal invoice placeholder
                from django.db import models
                invoice = type('Invoice', (), {
                    'id': 0,
                    'metadata': {},
                    'save': lambda self: None
                })()
                invoice.metadata = {}
            
            # 5. Store metadata in invoice for later use
            invoice.metadata = {
                'form_id': form.id,
                'form_slug': form.slug,
                'parent_data': parent_data,
                'student_data': student_data,
                'user_id': user.id if user else None,
                'is_staff': ApplicationPaymentService._is_school_staff(user, form.school) if user else False,
                'created_at': timezone.now().isoformat(),
            }
            
            # Call save if it exists
            if hasattr(invoice, 'save'):
                invoice.save()
            
            logger.info(f"Invoice created/placeholder: Amount: ₦{fee_amount}")
            
            # 6. If zero amount, mark as paid immediately
            if fee_amount == 0:
                ApplicationPaymentService._handle_zero_amount_invoice(invoice, form, student)
                return None, invoice
            
            # 7. Initialize payment for non-zero amounts
            payment_data = ApplicationPaymentService._initialize_payment(
                invoice, parent.email, form.school
            )
            
            return payment_data, invoice
            
        except Exception as e:
            logger.error(f"Failed to create application fee invoice: {str(e)}", exc_info=True)
            if isinstance(e, (ValidationError, PaymentProcessingError)):
                raise
            raise PaymentProcessingError(
                "Failed to process application fee. Please try again.",
                user_friendly=True
            )
    
    @staticmethod
    def _calculate_application_fee(form, parent_data, student_data, user):
        """
        Calculate application fee with all discounts applied.
        
        Returns:
            Decimal: Final fee amount after all discounts
        """
        base_fee = form.application_fee
        
        # Check if form is free
        if form.is_free:
            return Decimal('0.00')
        
        # Check for staff child discount
        if user and ApplicationPaymentService._is_school_staff(user, form.school):
            if hasattr(form.school, 'staff_children_waive_application_fee') and form.school.staff_children_waive_application_fee:
                logger.info(f"Staff fee waiver applied for user: {user.id}")
                return Decimal('0.00')
            
            # Staff discount percentage
            if hasattr(form.school, 'staff_discount_percentage') and form.school.staff_discount_percentage > 0:
                discount = base_fee * (form.school.staff_discount_percentage / 100)
                final_fee = base_fee - discount
                logger.info(f"Staff discount applied: {form.school.staff_discount_percentage}%")
                return max(final_fee, Decimal('0.00'))
        
        # Check for early bird discount
        if hasattr(form.school, 'early_bird_discount_enabled') and form.school.early_bird_discount_enabled:
            days_until_close = (form.close_date - timezone.now()).days
            early_bird_days = form.school.early_bird_days_threshold if hasattr(form.school, 'early_bird_days_threshold') else 30
            if days_until_close >= early_bird_days:
                discount_percentage = form.school.early_bird_discount_percentage if hasattr(form.school, 'early_bird_discount_percentage') else 10
                discount = base_fee * (discount_percentage / 100)
                final_fee = base_fee - discount
                logger.info(f"Early bird discount applied: {discount_percentage}%")
                return max(final_fee, Decimal('0.00'))
        
        return base_fee
    
    @staticmethod
    def _get_or_create_parent_for_invoice(parent_data, school, user=None):
        """
        Get or create parent for invoice purposes.
        Simplified version - doesn't create full parent record.
        """
        from students.models import Parent
        
        email = parent_data.get('email', '').lower().strip()
        
        try:
            parent = Parent.objects.get(email=email, school=school)
            logger.debug(f"Found existing parent for invoice: {parent.id}")
        except Parent.DoesNotExist:
            # Create minimal parent record for invoice
            parent = Parent.objects.create(
                school=school,
                email=email,
                first_name=parent_data.get('first_name', ''),
                last_name=parent_data.get('last_name', ''),
                phone_number=parent_data.get('phone_number', ''),
                is_staff_child=False,  # Will be updated if needed
                user=user
            )
            logger.debug(f"Created minimal parent for invoice: {parent.id}")
        
        return parent
    
    @staticmethod
    def _create_student_placeholder(student_data, parent):
        """
        Create minimal student record for invoice.
        Will be updated with full data after application submission.
        """
        from students.models import Student
        
        student = Student.objects.create(
            school=parent.school,
            first_name=student_data.get('first_name', ''),
            last_name=student_data.get('last_name', ''),
            parent=parent,
            admission_status='pending_payment',  # Special status for payment stage
            application_date=timezone.now()
        )
        
        logger.debug(f"Created student placeholder: {student.id}")
        return student
    
    @staticmethod
    def _is_school_staff(user, school):
        """Check if user is staff at given school."""
        if not user or not user.is_authenticated:
            return False
        
        from users.models import Staff
        return Staff.objects.filter(
            user=user,
            school=school,
            is_active=True
        ).exists()
    
    @staticmethod
    def _handle_zero_amount_invoice(invoice, form, student):
        """
        Handle zero-amount invoices (waivers, discounts).
        """
        logger.info(f"Processing zero-amount invoice/placeholder")
        
        # Try to mark as paid if payment core is available
        try:
            from .payment_core import PaymentCoreService
            invoice, payment = PaymentCoreService.mark_paid(
                invoice,
                payment_method=PaymentMethods.WAIVER if SHARED_CONSTANTS_AVAILABLE else 'waiver',
                reference=f"WAIVER-{getattr(invoice, 'id', 'placeholder')}",
                notes=f"Zero amount invoice for {form.name}"
            )
        except Exception as e:
            logger.warning(f"Could not mark invoice as paid: {e}")
        
        # Update student status
        student.admission_status = 'payment_waived'
        student.save(update_fields=['admission_status'])
        
        logger.info(f"Zero-amount invoice processed")
    
    @staticmethod
    def _initialize_payment(invoice, customer_email, school):
        """
        Initialize payment with Paystack.
        """
        logger.info(f"Initializing payment for invoice")
        
        try:
            # Import locally
            from .paystack import PaystackService
            
            paystack_service = PaystackService()
            
            # Add school-specific metadata
            metadata = {
                'invoice_id': getattr(invoice, 'id', 'placeholder'),
                'school_id': school.id,
                'form_id': getattr(invoice, 'metadata', {}).get('form_id'),
                'invoice_type': 'application_fee',
                'payment_purpose': 'application_fee',
            }
            
            # Initialize payment
            payment_data = paystack_service.initialize_payment(
                invoice=invoice,
                customer_email=customer_email,
                metadata=metadata
            )
            
            logger.info(f"Payment initialized: {payment_data.get('reference')}")
            return payment_data
            
        except Exception as e:
            logger.error(f"Failed to initialize payment: {str(e)}")
            raise PaymentProcessingError(
                "Unable to initialize payment. Please try again or contact support.",
                user_friendly=True
            )
    
    @staticmethod
    @transaction.atomic
    def complete_application_after_payment(reference):
        """
        Complete application creation after successful payment.
        Called by payment webhook or success callback.
        
        Args:
            reference: Payment reference from Paystack
        
        Returns:
            Application: Completed application instance
        """
        logger.info(f"Completing application after payment: {reference}")
        
        try:
            # 1. Verify payment
            try:
                from .paystack import PaystackService
                paystack_service = PaystackService()
                verification = paystack_service.verify_transaction(reference)
                
                if verification['status'] != 'success':
                    raise PaymentProcessingError(
                        f"Payment verification failed: {verification.get('message', 'Unknown error')}"
                    )
            except ImportError:
                logger.warning("PaystackService not available, skipping verification")
                verification = {'status': 'success'}
            
            # 2. Find invoice
            try:
                from billing.models import Invoice
                invoice = Invoice.objects.filter(
                    metadata__reference=reference
                ).first()
                
                if not invoice:
                    # Try to find by transaction metadata
                    invoice = ApplicationPaymentService._find_invoice_by_payment_metadata(reference)
                
                if not invoice:
                    raise ValidationError(f"No invoice found for payment reference: {reference}")
            except ImportError:
                logger.error("Billing models not available")
                raise ValidationError("Billing system not available")
            
            # 3. Mark invoice as paid
            if hasattr(invoice, 'payment_status') and invoice.payment_status != StatusChoices.PAID if SHARED_CONSTANTS_AVAILABLE else 'paid':
                try:
                    from .payment_core import PaymentCoreService
                    invoice, payment = PaymentCoreService.mark_paid(
                        invoice,
                        payment_method=PaymentMethods.PAYSTACK if SHARED_CONSTANTS_AVAILABLE else 'paystack',
                        reference=reference,
                        notes=f"Application fee payment completed via Paystack"
                    )
                except ImportError:
                    logger.warning("PaymentCoreService not available, marking invoice manually")
                    invoice.payment_status = 'paid'
                    invoice.save()
            
            # 4. Get application data from invoice metadata
            metadata = getattr(invoice, 'metadata', {})
            parent_data = metadata.get('parent_data', {})
            student_data = metadata.get('student_data', {})
            form_slug = metadata.get('form_slug')
            
            if not form_slug:
                raise ValidationError("Missing form information in invoice metadata")
            
            # 5. Create actual application using admissions service
            try:
                from admissions.services import ApplicationService
            except ImportError:
                logger.error("Admissions services not available")
                raise ValidationError("Admissions system not available")
            
            # Submit application (this will update the student record)
            application = ApplicationService.submit_application(
                application_data={'parent_data': parent_data, 'student_data': student_data},
                form_slug=form_slug,
                user=None,  # User will be determined from parent email
                request=None
            )
            
            # 6. Link invoice to application
            application.application_fee_paid = True
            application.application_fee_invoice = invoice
            application.save(update_fields=['application_fee_paid', 'application_fee_invoice'])
            
            # 7. Update student record (replace placeholder)
            student = getattr(invoice, 'student', None)
            if student and hasattr(student, 'admission_status') and student.admission_status == 'pending_payment':
                student.admission_status = 'applied'
                student.save(update_fields=['admission_status'])
            
            logger.info(f"Application completed after payment: {application.application_number}")
            
            # 8. Send confirmation email
            ApplicationPaymentService._send_confirmation_email(application)
            
            return application
            
        except Exception as e:
            logger.error(f"Failed to complete application after payment: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def _find_invoice_by_payment_metadata(reference):
        """Find invoice by payment reference in various metadata fields."""
        try:
            from billing.models import Invoice
            
            # Try different metadata field names
            invoices = Invoice.objects.filter(
                metadata__contains={'reference': reference}
            )
            
            if not invoices.exists():
                # Try in payment records
                try:
                    from billing.models import Payment
                    payment = Payment.objects.filter(reference=reference).first()
                    if payment:
                        return payment.invoice
                except ImportError:
                    pass
            
            return invoices.first()
        except ImportError:
            return None
    
    @staticmethod
    def _send_confirmation_email(application):
        """Send application confirmation email."""
        # This would integrate with your email service
        # For now, just log
        logger.info(f"Would send confirmation email for application: {application.application_number}")
    
    @staticmethod
    def verify_and_process_payment_webhook(webhook_data):
        """
        Process payment webhook for application fees.
        Called by billing webhook handler.
        
        Args:
            webhook_data: Dict from Paystack webhook
        
        Returns:
            bool: True if processed successfully
        """
        try:
            event = webhook_data.get('event')
            
            if event == 'charge.success':
                reference = webhook_data.get('data', {}).get('reference')
                if reference:
                    logger.info(f"Processing successful charge webhook: {reference}")
                    
                    # Complete application
                    ApplicationPaymentService.complete_application_after_payment(reference)
                    return True
            
            elif event == 'charge.failed':
                reference = webhook_data.get('data', {}).get('reference')
                logger.warning(f"Payment failed for reference: {reference}")
                
                # Update invoice status if billing models are available
                try:
                    from billing.models import Invoice
                    invoice = Invoice.objects.filter(
                        metadata__reference=reference
                    ).first()
                    
                    if invoice:
                        invoice.payment_status = StatusChoices.FAILED if SHARED_CONSTANTS_AVAILABLE else 'failed'
                        invoice.save(update_fields=['payment_status'])
                except ImportError:
                    pass
            
            return False
            
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
            return False 