# billing/services.py
import requests
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from core.exceptions import PaymentProcessingError

import time
from django.db import transaction
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

class IdempotencyService:
    """Prevent duplicate webhook processing."""
    
    @staticmethod
    def get_webhook_key(webhook_data):
        """Generate unique key for webhook idempotency."""
        event = webhook_data.get('event')
        webhook_id = webhook_data.get('webhook_id')
        reference = webhook_data.get('data', {}).get('reference', '')
        
        return f"webhook_{event}_{webhook_id}_{reference}"
    
    @staticmethod
    def check_duplicate(webhook_data):
        """Check if webhook was already processed."""
        key = IdempotencyService.get_webhook_key(webhook_data)
        return cache.get(key) is not None
    
    @staticmethod
    def mark_processed(webhook_data, ttl=24*60*60):  # 24 hours
        """Mark webhook as processed."""
        key = IdempotencyService.get_webhook_key(webhook_data)
        cache.set(key, True, ttl)

class BillingService:
    """Production-ready billing service with comprehensive error handling."""
    
    @staticmethod
    @transaction.atomic
    def process_payment_webhook(webhook_data):
        """
        Process payment webhook with idempotency and atomic transactions.
        """
        webhook_id = webhook_data.get('webhook_id', 'unknown')
        
        try:
            # === IDEMPOTENCY CHECK ===
            if IdempotencyService.check_duplicate(webhook_data):
                logger.warning(f"[{webhook_id}] Duplicate webhook detected, skipping")
                return True  # Return success for duplicates
            
            event = webhook_data['event']
            data = webhook_data['data']
            
            if event == 'charge.success':
                return BillingService._handle_successful_charge(data, webhook_id)
            elif event == 'charge.failed':
                return BillingService._handle_failed_charge(data, webhook_id)
            elif event == 'transfer.success':
                return BillingService._handle_transfer_success(data, webhook_id)
            else:
                logger.info(f"[{webhook_id}] Unhandled event type: {event}")
                return True  # Success for unhandled but valid events
                
        except Exception as e:
            logger.error(f"[{webhook_id}] Webhook processing error: {str(e)}")
            raise  # Re-raise to trigger transaction rollback
    
    @staticmethod
    def _handle_successful_charge(data, webhook_id):
        """Handle successful charge webhook."""
        from .models import Transaction, Invoice
        
        reference = data.get('reference')
        if not reference:
            logger.error(f"[{webhook_id}] No reference in charge.success webhook")
            return False
        
        try:
            # Find transaction
            transaction = Transaction.objects.select_related('invoice').get(
                paystack_reference=reference
            )
            
            # Prevent duplicate processing
            if transaction.status == 'success':
                logger.info(f"[{webhook_id}] Transaction already processed: {reference}")
                return True
            
            # Update transaction
            transaction.status = 'success'
            transaction.completed_at = timezone.now()
            transaction.paystack_response = data
            transaction.channel = data.get('channel', '')
            transaction.school_amount = Decimal(str(data.get('amount', 0))) / 100 - transaction.platform_fee - transaction.paystack_fee
            transaction.save()
            
            # Update invoice
            invoice = transaction.invoice
            invoice.status = 'paid'
            invoice.paid_date = timezone.now().date()
            invoice.paystack_reference = reference
            invoice.save()
            
            # Mark as processed
            IdempotencyService.mark_processed({
                'event': 'charge.success',
                'webhook_id': webhook_id,
                'data': {'reference': reference}
            })
            
            logger.info(f"[{webhook_id}] Successfully processed payment: {reference} for invoice {invoice.invoice_number}")
            
            # Trigger post-payment actions
            BillingService._trigger_post_payment_actions(invoice, webhook_id)
            
            return True
            
        except Transaction.DoesNotExist:
            logger.error(f"[{webhook_id}] Transaction not found: {reference}")
            return False
        except Exception as e:
            logger.error(f"[{webhook_id}] Error processing successful charge: {str(e)}")
            return False
    
    @staticmethod
    def _trigger_post_payment_actions(invoice, webhook_id):
        """Trigger actions after successful payment."""
        try:
            # Update application status if it's an application fee
            if (invoice.invoice_type == 'application' and 
                hasattr(invoice, 'application_fee_invoice')):
                
                application = invoice.application_fee_invoice
                application.application_fee_paid = True
                application.save()
                logger.info(f"[{webhook_id}] Application fee paid: {application.application_number}")
            
            # Update admission status if it's an acceptance fee
            if (invoice.invoice_type == 'acceptance' and 
                hasattr(invoice, 'acceptance_fee_invoice')):
                
                admission = invoice.acceptance_fee_invoice
                admission.acceptance_fee_paid = True
                admission.accepted = True
                admission.accepted_at = timezone.now()
                admission.save()
                logger.info(f"[{webhook_id}] Admission accepted: {admission.admission_number}")
            
            # Send payment confirmation (to be implemented)
            # EmailService.send_payment_confirmation(invoice)
            
        except Exception as e:
            logger.error(f"[{webhook_id}] Error in post-payment actions: {str(e)}")
            # Don't fail the webhook for post-payment errors


class PaystackService:
    """Paystack integration service with comprehensive error handling."""
    
    BASE_URL = "https://api.paystack.co"
    TIMEOUT = 30  # seconds
    
    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY')
        if not self.secret_key:
            logger.error("Paystack secret key not configured")
            raise PaymentProcessingError("Payment service not configured. Please contact support.", user_friendly=True)
    
    def _make_request(self, method, endpoint, data=None, retries=3):
        """Make authenticated request to Paystack API with retry logic."""
        for attempt in range(retries):
            try:
                url = f"{self.BASE_URL}{endpoint}"
                headers = {
                    'Authorization': f'Bearer {self.secret_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Edusuite/1.0'
                }
                
                logger.debug(f"Paystack API Request: {method} {endpoint}")
                
                response = requests.request(
                    method, 
                    url, 
                    json=data, 
                    headers=headers,
                    timeout=self.TIMEOUT
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.debug(f"Paystack API Response: {result.get('status')}")
                return result
                
            except requests.exceptions.Timeout:
                logger.warning(f"Paystack API timeout (attempt {attempt + 1}/{retries})")
                if attempt == retries - 1:
                    raise PaymentProcessingError(
                        "Payment service timeout. Please try again.",
                        user_friendly=True
                    )
                
            except requests.exceptions.ConnectionError:
                logger.warning(f"Paystack API connection error (attempt {attempt + 1}/{retries})")
                if attempt == retries - 1:
                    raise PaymentProcessingError(
                        "Network error. Please check your connection and try again.",
                        user_friendly=True
                    )
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Paystack API request error: {str(e)}")
                if attempt == retries - 1:
                    raise PaymentProcessingError(
                        "Payment service temporarily unavailable. Please try again.",
                        user_friendly=True
                    )
                
            except Exception as e:
                logger.error(f"Unexpected Paystack API error: {str(e)}")
                if attempt == retries - 1:
                    raise PaymentProcessingError(
                        "An unexpected error occurred. Please try again.",
                        user_friendly=True
                    )
    
    def initialize_payment(self, invoice, customer_email, metadata=None):
        """Initialize payment with Paystack."""
        try:
            # Convert amount to kobo (smallest currency unit)
            amount_kobo = int(invoice.total_amount * 100)
            
            data = {
                'email': customer_email,
                'amount': amount_kobo,
                'reference': f"EDU{invoice.id}{timezone.now().strftime('%Y%m%d%H%M%S')}",
                'metadata': {
                    'invoice_id': invoice.id,
                    'school_id': invoice.school.id,
                    'parent_id': invoice.parent.id,
                    'student_id': invoice.student.id if invoice.student else None,
                    'invoice_type': invoice.invoice_type,
                    'custom_fields': [
                        {
                            'display_name': "Invoice Number",
                            'variable_name': "invoice_number", 
                            'value': invoice.invoice_number
                        },
                        {
                            'display_name': "School Name", 
                            'variable_name': "school_name",
                            'value': invoice.school.name
                        }
                    ]
                },
                'channels': ['card', 'bank', 'ussd', 'qr', 'mobile_money'],
                'currency': 'NGN',
            }
            
            # Add subaccount for split payment if available
            if invoice.school.paystack_subaccount_id:
                data['subaccount'] = invoice.school.paystack_subaccount_id
                data['bearer'] = 'subaccount'
            
            if metadata:
                data['metadata'].update(metadata)
            
            result = self._make_request('POST', '/transaction/initialize', data)
            
            if result.get('status'):
                payment_data = result['data']
                
                # Create transaction record
                from .models import Transaction
                Transaction.objects.create(
                    invoice=invoice,
                    paystack_reference=payment_data['reference'],
                    amount=invoice.total_amount,
                    platform_fee=invoice.platform_fee,
                    paystack_fee=invoice.paystack_fee,
                    school_amount=invoice.total_amount - invoice.platform_fee - invoice.paystack_fee,
                    status='pending',
                    metadata=data['metadata']
                )
                
                logger.info(f"Payment initialized for invoice {invoice.invoice_number}: {payment_data['reference']}")
                
                return {
                    'authorization_url': payment_data['authorization_url'],
                    'access_code': payment_data['access_code'],
                    'reference': payment_data['reference']
                }
            else:
                logger.error(f"Paystack initialization failed: {result.get('message')}")
                raise PaymentProcessingError(
                    "Failed to initialize payment. Please try again.",
                    user_friendly=True
                )
                
        except PaymentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Payment initialization error: {str(e)}")
            raise PaymentProcessingError(
                "An error occurred while initializing payment. Please try again.",
                user_friendly=True
            )
    
    def verify_transaction(self, reference):
        """Verify Paystack transaction with comprehensive validation."""
        try:
            result = self._make_request('GET', f'/transaction/verify/{reference}')
            
            if result.get('status'):
                transaction_data = result['data']
                
                if transaction_data['status'] == 'success':
                    # Calculate split amounts
                    amount_ngn = transaction_data['amount'] / 100  # Convert from kobo
                    fees_ngn = transaction_data.get('fees', 0) / 100
                    school_amount = amount_ngn - fees_ngn
                    
                    return {
                        'status': 'success',
                        'amount': amount_ngn,
                        'school_amount': school_amount,
                        'fees': fees_ngn,
                        'paid_at': transaction_data.get('paid_at'),
                        'channel': transaction_data.get('channel'),
                        'currency': transaction_data.get('currency'),
                        'metadata': transaction_data.get('metadata', {})
                    }
                else:
                    return {
                        'status': 'failed',
                        'message': transaction_data.get('gateway_response', 'Payment failed'),
                        'transaction_data': transaction_data
                    }
            else:
                return {
                    'status': 'error',
                    'message': result.get('message', 'Verification failed')
                }
                
        except Exception as e:
            logger.error(f"Transaction verification error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def create_subaccount(self, school):
        """Create Paystack subaccount for school with split payments."""
        try:
            data = {
                'business_name': school.name[:255],  # Paystack limit
                'bank_code': school.bank_code,
                'account_number': school.account_number,
                'percentage_charge': 1.5,  # Platform commission
                'description': f"School account for {school.name}",
                'primary_contact_email': school.contact_email,
                'primary_contact_name': f"{school.name} Admin",
                'settlement_schedule': 'weekly',  # Weekly payouts to school
                'metadata': {
                    'school_id': school.id,
                    'school_type': school.school_type
                }
            }
            
            if school.phone_number:
                data['primary_contact_phone'] = school.phone_number
            
            result = self._make_request('POST', '/subaccount', data)
            
            if result.get('status'):
                subaccount_id = result['data']['subaccount_code']
                logger.info(f"Paystack subaccount created: {subaccount_id} for school {school.id}")
                return subaccount_id
            else:
                error_message = result.get('message', 'Unknown error')
                logger.error(f"Paystack subaccount creation failed: {error_message}")
                raise PaymentProcessingError(
                    "Failed to create payment account. Please check your bank details.",
                    user_friendly=True
                )
                
        except PaymentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Subaccount creation error: {str(e)}")
            raise PaymentProcessingError(
                "Unable to setup payment system. Please contact support.",
                user_friendly=True
            )
            
            
# billing/services.py - PAYMENT SECURITY
class PaymentSecurity:
    """Advanced payment security measures."""
    
    @staticmethod
    def validate_payment_amount(invoice, amount_from_paystack):
        """Validate that payment amount matches invoice amount."""
        try:
            # Convert to same precision
            invoice_amount = Decimal(str(invoice.total_amount))
            paystack_amount = Decimal(str(amount_from_paystack)) / 100  # Convert from kobo
            
            # Allow small rounding differences (1 Naira)
            amount_difference = abs(invoice_amount - paystack_amount)
            
            if amount_difference > Decimal('1.00'):
                logger.warning(
                    f"Amount mismatch for invoice {invoice.invoice_number}: "
                    f"Invoice: ₦{invoice_amount}, Paystack: ₦{paystack_amount}"
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Amount validation error: {str(e)}")
            return False
    
    @staticmethod
    def check_duplicate_payment(reference, invoice_id):
        """Check for duplicate payments."""
        from .models import Transaction
        
        existing_success = Transaction.objects.filter(
            paystack_reference=reference,
            status='success'
        ).exists()
        
        if existing_success:
            logger.warning(f"Duplicate successful transaction detected: {reference}")
            return True
        
        # Check for multiple successful transactions for same invoice
        invoice_success_count = Transaction.objects.filter(
            invoice_id=invoice_id,
            status='success'
        ).count()
        
        if invoice_success_count >= 1:
            logger.warning(f"Multiple successful transactions for invoice {invoice_id}")
            return True
        
        return False
    
    @staticmethod
    def sanitize_payment_metadata(metadata):
        """Sanitize payment metadata to prevent injection attacks."""
        safe_metadata = {}
        
        allowed_fields = {
            'invoice_id', 'school_id', 'parent_id', 'student_id', 
            'invoice_type', 'invoice_number', 'school_name'
        }
        
        for key, value in metadata.items():
            if key in allowed_fields:
                # Basic sanitization
                if isinstance(value, str):
                    safe_metadata[key] = value.strip()[:500]  # Limit length
                else:
                    safe_metadata[key] = value
        
        return safe_metadata