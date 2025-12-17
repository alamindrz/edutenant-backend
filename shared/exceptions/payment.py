# shared/exceptions/payment.py
"""
Payment-related exceptions.
"""


class PaymentProcessingError(Exception):
    """Exception raised for payment processing errors."""
    
    def __init__(self, message, user_friendly=False, original_error=None):
        self.message = message
        self.user_friendly = user_friendly
        self.original_error = original_error
        super().__init__(self.message)


class PaymentVerificationError(Exception):
    """Exception raised when payment verification fails."""
    pass


class InsufficientFundsError(Exception):
    """Exception raised when account has insufficient funds."""
    pass


class PaymentGatewayError(Exception):
    """Exception raised when payment gateway returns an error."""
    pass