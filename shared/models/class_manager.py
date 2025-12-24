# shared/models/class_manager.py
"""
SINGLE SOURCE for Class resolution. KILLS ClassGroup references.
DEPENDS ON: Django, shared.constants
"""
from django.core.exceptions import ObjectDoesNotExist

# Import constants directly, NOT through shared.__init__
from shared.constants.model_fields import CLASS_MODEL_PATH
# Import FieldMapper directly
from shared.utils.field_mapping import FieldMapper

class ClassManager:
    """Manager for Class operations. Use this instead of direct Class references."""

    @staticmethod
    def get_class(class_id, school=None, raise_exception=True):
        # Lazy import inside method to avoid circular imports
        from core.models import Class
        try:
            if school:
                return Class.objects.get(id=class_id, school=school)
            return Class.objects.get(id=class_id)
        except (Class.DoesNotExist, ValueError):
            if raise_exception:
                raise ObjectDoesNotExist(f"Class with id {class_id} not found")
            return None

    @staticmethod
    def validate_class_availability(class_id, school, is_staff=False):
        try:
            class_instance = ClassManager.get_class(class_id, school)
            if is_staff:
                return True, "Staff priority registration", class_instance

            current_students = class_instance.students.count()
            if current_students >= class_instance.capacity:
                return False, "Class is at full capacity", class_instance
            return True, "Class has available space", class_instance
        except ObjectDoesNotExist:
            return False, "Class not found", None

    @staticmethod
    def prepare_class_data(form_data):
        data = form_data.copy()
        # Use FieldMapper directly
        class_id, _ = FieldMapper.extract_class_id(data)
        if class_id:
            for field in ['current_class_id', 'class_id', 'class', 'class_group_id', 'class_group']:
                data.pop(field, None)
            data['current_class_id'] = class_id
        return data

    @staticmethod
    def get_class_choices(school):
        # Lazy import
        from core.models import Class
        classes = Class.objects.filter(school=school).order_by('name')
        return [(c.id, c.name) for c in classes]
