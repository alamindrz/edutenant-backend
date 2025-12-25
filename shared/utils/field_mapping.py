# shared/utils/field_mapping.py
"""
Consistent field mapping across all forms and APIs.
DEPENDS ONLY ON: shared.constants
"""
from shared.constants.model_fields import FORM_TO_MODEL

import logging

logger = logging.getLogger(__name__)

class FieldMapper:
    """Handle field name standardization and mapping."""

    # Centralized mapping configuration
    MAPS = {
        'student': {
            'first_name': 'first_name',
            'surname': 'last_name',
            'date_of_birth': 'dob',
        },
        'parent': {
            'phone': 'phone_number',
            'email_address': 'email',
        },
        'application': {
            'applied_class': 'applied_class_id',
        }
    }

    @staticmethod
    def map_form_to_model(form_data, model_name=None):
        """
        Apply consistent field mapping from forms to models.
        """
        if not form_data:
            return {}

        # FIXED: Create a new dict instead of modifying the copy in a loop
        standardized_data = {}
        
        # Get the specific map for the model, or an empty dict if not found
        # This addresses the CodeRabbit "Minor comment" about missing defaults
        mapping = FieldMapper.MAPS.get(model_name, {})

        for key, value in form_data.items():
            # If the key exists in our map, use the model field name
            new_key = mapping.get(key, key)
            standardized_data[new_key] = value

        # Standardize phone number if present
        if 'phone_number' in standardized_data:
            standardized_data['phone_number'] = FieldMapper.standardize_phone_number(
                standardized_data['phone_number']
            )

        return standardized_data

    @staticmethod
    def standardize_phone_number(phone):
        """Placeholder for your phone standardization logic."""
        if not phone:
            return phone
        return str(phone).strip().replace(" ", "")

    @staticmethod
    def standardize_phone_number(phone):
        """Standardize phone number format for Nigeria."""
        if not phone:
            return ""

        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, str(phone)))

        # If empty after cleaning, return empty
        if not digits:
            return ""

        # Format for Nigeria:
        # 08012345678 → 2348012345678
        # 8012345678 → 2348012345678
        # 2348012345678 → 2348012345678 (already correct)

        if digits.startswith('0') and len(digits) == 11:
            # 08012345678 → 2348012345678
            return '234' + digits[1:]
        elif digits.startswith('234') and len(digits) == 13:
            # Already in international format
            return digits
        elif len(digits) == 10:
            # 8012345678 → 2348012345678
            return '234' + digits
        else:
            # Return as-is, might be international number
            return digits

    @staticmethod
    def extract_class_id(form_data):
        """
        Extract class ID from form data regardless of field name.
        Returns (class_id, found_field_name)
        """
        class_fields = ['current_class_id', 'class_id', 'class', 'class_group_id', 'class_group']

        for field in class_fields:
            if field in form_data and form_data[field]:
                class_id = form_data[field]
                # Handle both ID and object
                if hasattr(class_id, 'id'):
                    return class_id.id, field
                return class_id, field

        return None, None
