"""
SINGLE PaystackService - consolidated from billing and admissions.
Handles ALL Paystack API interactions with proper error handling and retry logic.
"""
import logging
import requests
import hmac
import hashlib
import json
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from typing import Dict, Any, Optional, Tuple

from shared.exceptions.payment import (
    PaymentProcessingError,
    PaymentVerificationError,
    PaymentGatewayError
)

logger = logging.getLogger(__name__)


class PaystackService:
    """
    Consolidated Paystack service with all functionality.
    Used by both admissions and billing apps.
    """

    BASE_URL = "https://api.paystack.co"
    TIMEOUT = 30
    MAX_RETRIES = 3

    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        self.public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')

        if not self.secret_key:
            logger.error("Paystack secret key not configured")
            raise PaymentProcessingError(
                "Payment service not configured. Please contact support.",
                user_friendly=True
            )

    def _make_request(self, method: str, endpoint: str, data: Dict = None,
                     retry_count: int = 0) -> Dict[str, Any]:
        """
        Make authenticated request to Paystack API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request data
            retry_count: Current retry attempt

        Returns:
            Dict: Response data

        Raises:
            PaymentGatewayError: If API request fails
        """
        try:
            url = f"{self.BASE_URL}{endpoint}"
            headers = {
                'Authorization': f'Bearer {self.secret_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'Edusuite/1.0'
            }

            logger.debug(f"Paystack {method} {endpoint} - Attempt {retry_count + 1}")

            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=headers,
                timeout=self.TIMEOUT
            )

            # Log rate limit headers for debugging
            if 'X-RateLimit-Remaining' in response.headers:
                remaining = response.headers['X-RateLimit-Remaining']
                logger.debug(f"Rate limit remaining: {remaining}")

            response.raise_for_status()
            result = response.json()

            if not result.get('status', False):
                error_message = result.get('message', 'Unknown Paystack error')
                logger.error(f"Paystack API error: {error_message}")
                raise PaymentGatewayError(f"Paystack error: {error_message}")

            return result

        except requests.exceptions.Timeout:
            if retry_count < self.MAX_RETRIES - 1:
                logger.warning(f"Paystack timeout, retrying ({retry_count + 1}/{self.MAX_RETRIES})")
                return self._make_request(method, endpoint, data, retry_count + 1)
            logger.error("Paystack timeout after all retries")
            raise PaymentGatewayError(
                "Payment service timeout. Please try again.",
                user_friendly=True
            )

        except requests.exceptions.ConnectionError:
            if retry_count < self.MAX_RETRIES - 1:
                logger.warning(f"Paystack connection error, retrying ({retry_count + 1}/{self.MAX_RETRIES})")
                return self._make_request(method, endpoint, data, retry_count + 1)
            logger.error("Paystack connection error after all retries")
            raise PaymentGatewayError(
                "Network error. Please check your connection.",
                user_friendly=True
            )

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else 'Unknown'

            if status_code == 401:
                logger.error("Paystack authentication failed - invalid secret key")
                raise PaymentGatewayError(
                    "Payment service authentication failed.",
                    user_friendly=False
                )
            elif status_code == 422:
                # Validation error - return the error message
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', 'Validation error')
                    logger.error(f"Paystack validation error: {error_message}")
                    raise PaymentProcessingError(error_message, user_friendly=True)
                except:
                    raise PaymentProcessingError("Invalid payment data.", user_friendly=True)
            elif status_code == 429:
                logger.error("Paystack rate limit exceeded")
                raise PaymentGatewayError(
                    "Payment service busy. Please try again in a moment.",
                    user_friendly=True
                )
            elif 500 <= status_code < 600:
                if retry_count < self.MAX_RETRIES - 1:
                    logger.warning(f"Paystack server error {status_code}, retrying ({retry_count + 1}/{self.MAX_RETRIES})")
                    return self._make_request(method, endpoint, data, retry_count + 1)
                logger.error(f"Paystack server error after all retries: {status_code}")
                raise PaymentGatewayError(
                    "Payment service temporarily unavailable. Please try again.",
                    user_friendly=True
                )
            else:
                logger.error(f"Paystack HTTP error {status_code}: {str(e)}")
                raise PaymentGatewayError(
                    f"Payment service error: {status_code}",
                    user_friendly=True
                )

        except Exception as e:
            logger.error(f"Unexpected Paystack error: {str(e)}", exc_info=True)
            raise PaymentGatewayError(
                "Unexpected payment error. Please try again.",
                user_friendly=True
            )

    def initialize_payment(self, invoice, customer_email: str,
                          metadata: Dict = None) -> Dict[str, Any]:
        """
        Initialize payment for an invoice.

        Args:
            invoice: Invoice model instance
            customer_email: Customer email for Paystack
            metadata: Additional metadata

        Returns:
            Dict with payment data including authorization_url
        """
        try:
            # Validate invoice
            if not invoice.total_amount or invoice.total_amount <= 0:
                raise PaymentProcessingError(
                    "Invalid invoice amount.",
                    user_friendly=True
                )

            # Generate reference
            reference = self._generate_reference(invoice)

            # Prepare request data
            data = {
                'email': customer_email,
                'amount': int(invoice.total_amount * 100),  # Convert to kobo
                'reference': reference,
                'metadata': {
                    'invoice_id': invoice.id,
                    'invoice_number': getattr(invoice, 'invoice_number', ''),
                    'school_id': invoice.school.id if hasattr(invoice, 'school') else None,
                    'parent_id': invoice.parent.id if hasattr(invoice, 'parent') else None,
                    'student_id': invoice.student.id if hasattr(invoice, 'student') and invoice.student else None,
                    'invoice_type': getattr(invoice, 'invoice_type', 'unknown'),
                    'source': 'edusuite',
                }
            }

            # Add custom metadata if provided
            if metadata:
                data['metadata'].update(metadata)

            # Add split payment if school has subaccount
            if hasattr(invoice, 'school') and hasattr(invoice.school, 'paystack_subaccount_id'):
                subaccount_id = invoice.school.paystack_subaccount_id
                if subaccount_id:
                    data['subaccount'] = subaccount_id
                    data['bearer'] = 'subaccount'  # School bears transaction fees
                    logger.debug(f"Using subaccount: {subaccount_id}")

            # Add payment channels for Nigeria
            data['channels'] = ['card', 'bank', 'ussd', 'qr', 'mobile_money']

            # Make API call
            result = self._make_request('POST', '/transaction/initialize', data)

            if not result.get('status'):
                raise PaymentProcessingError(
                    "Failed to initialize payment. Please try again.",
                    user_friendly=True
                )

            payment_data = result['data']

            return {
                'authorization_url': payment_data['authorization_url'],
                'access_code': payment_data['access_code'],
                'reference': payment_data['reference'],
                'amount': invoice.total_amount,
                'currency': 'NGN',
                'metadata': data['metadata'],
            }

        except PaymentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize payment: {str(e)}", exc_info=True)
            raise PaymentProcessingError(
                "Failed to initialize payment. Please try again.",
                user_friendly=True
            )

    def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """
        Verify transaction status.

        Args:
            reference: Paystack transaction reference

        Returns:
            Dict with verification result
        """
        try:
            # Check cache first
            cache_key = f"paystack_verify_{reference}"
            cached_result = cache.get(cache_key)

            if cached_result:
                logger.debug(f"Using cached verification for {reference}")
                return cached_result

            # Make API call
            result = self._make_request('GET', f'/transaction/verify/{reference}')

            if not result.get('status'):
                raise PaymentVerificationError("Transaction verification failed")

            transaction_data = result['data']

            # Parse response
            verification_result = {
                'status': transaction_data['status'],
                'amount': transaction_data['amount'] / 100,  # Convert from kobo
                'currency': transaction_data['currency'],
                'channel': transaction_data.get('channel', ''),
                'paid_at': transaction_data.get('paid_at'),
                'metadata': transaction_data.get('metadata', {}),
                'fees': transaction_data.get('fees', 0) / 100,
                'reference': transaction_data.get('reference', reference),
                'customer': transaction_data.get('customer', {}),
                'authorization': transaction_data.get('authorization', {}),
            }

            # Cache successful verifications for 5 minutes
            if verification_result['status'] == 'success':
                cache.set(cache_key, verification_result, 300)

            return verification_result

        except PaymentVerificationError:
            raise
        except Exception as e:
            logger.error(f"Failed to verify transaction {reference}: {str(e)}")
            raise PaymentVerificationError(f"Failed to verify transaction: {str(e)}")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Paystack webhook signature.

        Args:
            payload: Raw request body
            signature: X-Paystack-Signature header value

        Returns:
            bool: True if signature is valid
        """
        try:
            if not signature or not self.secret_key:
                return False

            # Calculate HMAC SHA512
            computed_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            # Use compare_digest to prevent timing attacks
            return hmac.compare_digest(computed_signature, signature)

        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return False

    def create_transfer_recipient(self, name: str, account_number: str,
                                 bank_code: str, currency: str = 'NGN') -> Dict[str, Any]:
        """
        Create transfer recipient for payouts.

        Args:
            name: Recipient name
            account_number: Bank account number
            bank_code: Paystack bank code
            currency: Currency (default: NGN)

        Returns:
            Dict with recipient data
        """
        try:
            data = {
                'type': 'nuban',
                'name': name,
                'account_number': account_number,
                'bank_code': bank_code,
                'currency': currency
            }

            result = self._make_request('POST', '/transferrecipient', data)

            if not result.get('status'):
                raise PaymentGatewayError("Failed to create transfer recipient")

            return result['data']

        except Exception as e:
            logger.error(f"Failed to create transfer recipient: {str(e)}")
            raise PaymentGatewayError(f"Failed to create transfer recipient: {str(e)}")

    def initiate_transfer(self, amount: float, recipient: str,
                         reason: str = '', reference: str = None) -> Dict[str, Any]:
        """
        Initiate transfer to recipient.

        Args:
            amount: Amount to transfer (in Naira)
            recipient: Recipient code or ID
            reason: Transfer reason
            reference: Custom reference (optional)

        Returns:
            Dict with transfer data
        """
        try:
            data = {
                'source': 'balance',
                'amount': int(amount * 100),  # Convert to kobo
                'recipient': recipient,
                'reason': reason or 'School payment'
            }

            if reference:
                data['reference'] = reference

            result = self._make_request('POST', '/transfer', data)

            if not result.get('status'):
                raise PaymentGatewayError("Failed to initiate transfer")

            return result['data']

        except Exception as e:
            logger.error(f"Failed to initiate transfer: {str(e)}")
            raise PaymentGatewayError(f"Failed to initiate transfer: {str(e)}")

    def verify_transfer(self, reference: str) -> Dict[str, Any]:
        """
        Verify transfer status.

        Args:
            reference: Transfer reference

        Returns:
            Dict with transfer verification result
        """
        try:
            result = self._make_request('GET', f'/transfer/verify/{reference}')

            if not result.get('status'):
                raise PaymentVerificationError("Transfer verification failed")

            return result['data']

        except Exception as e:
            logger.error(f"Failed to verify transfer {reference}: {str(e)}")
            raise PaymentVerificationError(f"Failed to verify transfer: {str(e)}")

    def list_banks(self, country: str = 'nigeria') -> Dict[str, Any]:
        """
        List supported banks for a country.

        Args:
            country: Country code (default: nigeria)

        Returns:
            Dict with list of banks
        """
        try:
            cache_key = f"paystack_banks_{country}"
            cached_banks = cache.get(cache_key)

            if cached_banks:
                logger.debug(f"Using cached banks list for {country}")
                return cached_banks

            result = self._make_request('GET', f'/bank?country={country}')

            if not result.get('status'):
                raise PaymentGatewayError("Failed to fetch banks list")

            banks_data = {
                'status': result['status'],
                'message': result.get('message', ''),
                'data': result.get('data', [])
            }

            # Cache for 24 hours
            cache.set(cache_key, banks_data, 86400)

            return banks_data

        except Exception as e:
            logger.error(f"Failed to fetch banks list: {str(e)}")
            raise PaymentGatewayError(f"Failed to fetch banks list: {str(e)}")

    def resolve_account_number(self, account_number: str, bank_code: str) -> Dict[str, Any]:
        """
        Resolve bank account number to account name.

        Args:
            account_number: Bank account number
            bank_code: Paystack bank code

        Returns:
            Dict with account details
        """
        try:
            cache_key = f"paystack_resolve_{bank_code}_{account_number}"
            cached_result = cache.get(cache_key)

            if cached_result:
                logger.debug(f"Using cached account resolution for {account_number}")
                return cached_result

            result = self._make_request(
                'GET',
                f'/bank/resolve?account_number={account_number}&bank_code={bank_code}'
            )

            if not result.get('status'):
                raise PaymentGatewayError("Failed to resolve account number")

            account_data = result['data']

            # Cache for 1 hour
            cache.set(cache_key, account_data, 3600)

            return account_data

        except Exception as e:
            logger.error(f"Failed to resolve account number: {str(e)}")
            raise PaymentGatewayError(f"Failed to resolve account number: {str(e)}")

    def _generate_reference(self, invoice) -> str:
        """
        Generate unique reference for payment.

        Args:
            invoice: Invoice instance

        Returns:
            str: Unique reference
        """
        import uuid
        from django.utils.timezone import now

        # Generate base reference
        if hasattr(invoice, 'invoice_number'):
            base_ref = invoice.invoice_number.replace('/', '_')
        else:
            base_ref = f"INV{invoice.id}"

        # Add timestamp and random component
        timestamp = now().strftime('%Y%m%d%H%M%S')
        random_component = str(uuid.uuid4())[:8]

        return f"{base_ref}_{timestamp}_{random_component}"


    def health_check(self) -> Tuple[bool, str]:
        """
        Check Paystack API health.

        Returns:
            Tuple of (is_healthy: bool, message: str)
        """
        try:
            result = self._make_request('GET', '/bank?country=nigeria&perPage=1')

            if result.get('status'):
                return True, "Paystack API is healthy"
            else:
                return False, f"Paystack API error: {result.get('message', 'Unknown error')}"

        except Exception as e:
            return False, f"Paystack API unreachable: {str(e)}"
