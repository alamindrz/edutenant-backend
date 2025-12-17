"""
MODEL REGISTRY - Central registry for all model references
Prevents circular imports and provides single source of truth.
"""

from django.apps import apps

class ModelRegistry:
    """Registry for all model references in the system."""
    
    @staticmethod
    def get_model(app_label, model_name):
        """Safe way to get any model."""
        try:
            return apps.get_model(app_label, model_name)
        except LookupError as e:
            raise ImportError(f"Cannot import model {app_label}.{model_name}: {e}")
    
    @staticmethod
    def get_school_model():
        return apps.get_model('core', 'School')
    
    @staticmethod
    def get_class_model():
        return apps.get_model('core', 'Class')
    
    @staticmethod
    def get_user_model():
        return apps.get_model('users', 'User')
    
    @staticmethod
    def get_staff_model():
        return apps.get_model('users', 'Staff')
    
    @staticmethod
    def get_student_model():
        return apps.get_model('students', 'Student')
    
    @staticmethod
    def get_parent_model():
        return apps.get_model('students', 'Parent')
    
    @staticmethod
    def get_application_model():
        return apps.get_model('admissions', 'Application')


# Convenience functions
def get_school_model():
    return ModelRegistry.get_school_model()

def get_class_model():
    return ModelRegistry.get_class_model()

def get_user_model():
    return ModelRegistry.get_user_model()