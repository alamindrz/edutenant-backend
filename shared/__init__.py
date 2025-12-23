# shared/__init__.py
"""
Shared package - central access to constants, utils, and models.
Avoids importing services to prevent circular dependencies.
"""

# Constants
from .constants import (
    PARENT_PHONE_FIELD,
    STUDENT_CLASS_FIELD,
    CLASS_MODEL_PATH,
    FORM_TO_MODEL,
    StatusChoices,
    PaymentMethods
)

# Utilities
from .utils.field_mapping import FieldMapper

# Models
from .models import ClassManager

# Aliases for convenience
field_mapper = FieldMapper
class_manager = ClassManager

__all__ = [
    # Constants
    'PARENT_PHONE_FIELD',
    'STUDENT_CLASS_FIELD',
    'CLASS_MODEL_PATH',
    'FORM_TO_MODEL',
    'StatusChoices',
    'PaymentMethods',

    # Utilities
    'FieldMapper',
    'field_mapper',

    # Models
    'ClassManager',
    'class_manager',
] 