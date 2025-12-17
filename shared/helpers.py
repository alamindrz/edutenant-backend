# shared/helpers.py
"""
Safe import helpers to avoid circular imports.
"""
import sys

def get_field_mapper():
    """Safely get FieldMapper instance."""
    from shared.utils.field_mapping import FieldMapper
    return FieldMapper

def get_class_manager():
    """Safely get ClassManager instance."""
    from shared.models.class_manager import ClassManager
    return ClassManager

def get_application_payment_service():
    """Safely get ApplicationPaymentService instance."""
    from shared.services.payment.application_fee import ApplicationPaymentService
    return ApplicationPaymentService