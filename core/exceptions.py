# core/exceptions.py - FIXED
class SchoolManagementException(Exception):
    """Base exception for all school management system errors."""

    def __init__(self, message=None, user_friendly=False, details=None, error_code=None):
        self.message = message or "An error occurred"
        self.user_friendly = user_friendly
        self.details = details or {}
        self.error_code = error_code
        super().__init__(self.message)

class AuthenticationError(SchoolManagementException):
    """Authentication and authorization errors."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "Authentication failed", user_friendly, details, "AUTH_ERROR")

class ValidationError(SchoolManagementException):
    """Data validation errors."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "Validation failed", user_friendly, details, "VALIDATION_ERROR")

class PaymentProcessingError(SchoolManagementException):
    """Payment-related errors."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "Payment processing failed", user_friendly, details, "PAYMENT_ERROR")

class RolePermissionError(SchoolManagementException):
    """Authorization and permission-related errors."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "Insufficient permissions", user_friendly, details, "PERMISSION_ERROR")

class SchoolOnboardingError(SchoolManagementException):
    """Errors during school onboarding and setup."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "School setup failed", user_friendly, details, "ONBOARDING_ERROR")
