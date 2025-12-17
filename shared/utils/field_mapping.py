# shared/utils/field_mapping.py
"""
Consistent field mapping across all forms and APIs.
DEPENDS ONLY ON: shared.constants
"""
from shared.constants.model_fields import FORM_TO_MODEL

class FieldMapper:
    """Handle field name standardization and mapping."""
    
    @staticmethod
    def map_form_to_model(form_data, model_name=None):
        """
        Apply consistent field mapping from forms to models.
        
        Args:
            form_data (dict): Data from form.cleaned_data or request.POST
            model_name (str, optional): 'parent', 'student', 'application'
        
        Returns:
            dict: Standardized data with correct field names
        """
        if not form_data:
            return {}
            
        mapped_data = form_data.copy()
        
        # 1. Apply global form→model mapping
        for form_field, model_field in FORM_TO_MODEL.items():
            if form_field in mapped_data:
                mapped_data[model_field] = mapped_data.pop(form_field)
        
        # 2. Standardize phone number if present
        if 'phone_number' in mapped_data:
            mapped_data['phone_number'] = FieldMapper.standardize_phone_number(
                mapped_data['phone_number']
            )
        
        return mapped_data
    
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