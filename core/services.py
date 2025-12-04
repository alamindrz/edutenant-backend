# core/services.py
import logging
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Class, ClassCategory, ClassCreationTemplate
from core.exceptions import SchoolManagementException

logger = logging.getLogger(__name__)
User = get_user_model()


class ClassManagementService:
    """Service for managing school classes"""
    
    @staticmethod
    def create_class_category(school, name, section, description="", display_order=0):
        """Create a new class category."""
        try:
            category = ClassCategory.objects.create(
                school=school,
                name=name,
                section=section,
                description=description,
                display_order=display_order
            )
            logger.info(f"Created class category: {category.name} for school {school.name}")
            return category
        except Exception as e:
            logger.error(f"Failed to create class category: {e}")
            raise SchoolManagementException("Failed to create class category")
    
    @staticmethod
    @transaction.atomic
    def create_class(school, category, name, form_master=None, max_students=40, room_number="", academic_session=""):
        """Create a new class with validation."""
        # Validate class doesn't already exist
        if Class.objects.filter(school=school, name=name).exists():
            raise SchoolManagementException(f"Class '{name}' already exists in this school")
        
        # Validate form master belongs to school
        if form_master and form_master.school != school:
            raise SchoolManagementException("Form master must belong to the same school")
        
        try:
            class_instance = Class.objects.create(
                school=school,
                category=category,
                name=name,
                form_master=form_master,
                max_students=max_students,
                room_number=room_number,
                academic_session=academic_session
            )
            
            logger.info(f"Created class: {class_instance.name} for school {school.name}")
            return class_instance
            
        except Exception as e:
            logger.error(f"Failed to create class: {e}")
            raise SchoolManagementException("Failed to create class")
    
    @staticmethod
    def assign_form_master(class_instance, form_master, assigned_by):
        """Assign or change form master for a class."""
        if form_master.school != class_instance.school:
            raise SchoolManagementException("Form master must belong to the same school")
        
        class_instance.form_master = form_master
        class_instance.save()
        
        logger.info(f"Assigned {form_master.full_name} as form master for {class_instance.name}")
    
    @staticmethod
    def create_classes_from_template(school, school_type):
        """Automatically create classes based on school type template."""
        try:
            template = ClassCreationTemplate.objects.filter(
                school_type=school_type, 
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"No class template found for school type: {school_type}")
                return []
            
            created_classes = []
            config = template.configuration
            
            for category_config in config.get('categories', []):
                # Create category
                category = ClassManagementService.create_class_category(
                    school=school,
                    name=category_config['name'],
                    section=category_config['section'],
                    description=category_config.get('description', ''),
                    display_order=category_config.get('display_order', 0)
                )
                
                # Create classes for this category
                for class_config in category_config.get('classes', []):
                    class_instance = ClassManagementService.create_class(
                        school=school,
                        category=category,
                        name=class_config['name'],
                        max_students=class_config.get('max_students', 40),
                        room_number=class_config.get('room_number', '')
                    )
                    created_classes.append(class_instance)
            
            logger.info(f"Created {len(created_classes)} classes from template for school {school.name}")
            return created_classes
            
        except Exception as e:
            logger.error(f"Failed to create classes from template: {e}")
            raise SchoolManagementException("Failed to create classes from template")
    
    @staticmethod
    def get_classes_by_teacher(teacher):
        """Get all classes taught by a teacher."""
        return Class.objects.filter(
            school=teacher.school,
            is_active=True
        ).filter(
            models.Q(form_master=teacher) | 
            models.Q(assistant_form_master=teacher) |
            models.Q(classsubject__teacher=teacher)
        ).distinct()
    
    @staticmethod
    def deactivate_class(class_instance, deactivated_by):
        """Deactivate a class (soft delete)."""
        class_instance.is_active = False
        class_instance.save()
        
        logger.info(f"Deactivated class: {class_instance.name} by {deactivated_by.email}")


class ClassMonitorService:
    """Service for managing class monitors"""
    
    @staticmethod
    def assign_monitor(class_instance, student, role, assigned_by, responsibilities=None, notes=""):
        """Assign a student as class monitor."""
        from students.models import Student
        
        # Validate student belongs to the class
        if student.current_class != class_instance:
            raise SchoolManagementException("Student must belong to the class")
        
        # Check if role is already assigned
        existing_monitor = ClassMonitor.objects.filter(
            class_instance=class_instance,
            role=role,
            is_active=True
        ).first()
        
        if existing_monitor:
            raise SchoolManagementException(f"{role.title()} role is already assigned to {existing_monitor.student.full_name}")
        
        try:
            monitor = ClassMonitor.objects.create(
                class_instance=class_instance,
                student=student,
                role=role,
                assigned_by=assigned_by,
                responsibilities=responsibilities or [],
                notes=notes
            )
            
            logger.info(f"Assigned {student.full_name} as {role} for {class_instance.name}")
            return monitor
            
        except Exception as e:
            logger.error(f"Failed to assign monitor: {e}")
            raise SchoolManagementException("Failed to assign class monitor")
    
    @staticmethod
    def remove_monitor(monitor, removed_by):
        """Remove a class monitor."""
        monitor.is_active = False
        monitor.end_date = timezone.now().date()
        monitor.save()
        
        logger.info(f"Removed {monitor.student.full_name} as {monitor.role} from {monitor.class_instance.name}")


# Default class templates
DEFAULT_CLASS_TEMPLATES = {
    'nursery': {
        'categories': [
            {
                'name': 'Nursery',
                'section': 'nursery',
                'display_order': 1,
                'classes': [
                    {'name': 'Play Group', 'max_students': 20},
                    {'name': 'Nursery 1', 'max_students': 25},
                    {'name': 'Nursery 2', 'max_students': 25},
                    {'name': 'Nursery 3', 'max_students': 25},
                ]
            }
        ]
    },
    'primary': {
        'categories': [
            {
                'name': 'Primary',
                'section': 'primary',
                'display_order': 1,
                'classes': [
                    {'name': 'Primary 1A', 'max_students': 35},
                    {'name': 'Primary 1B', 'max_students': 35},
                    {'name': 'Primary 2A', 'max_students': 35},
                    {'name': 'Primary 2B', 'max_students': 35},
                    {'name': 'Primary 3A', 'max_students': 35},
                    {'name': 'Primary 3B', 'max_students': 35},
                    {'name': 'Primary 4A', 'max_students': 35},
                    {'name': 'Primary 4B', 'max_students': 35},
                    {'name': 'Primary 5A', 'max_students': 35},
                    {'name': 'Primary 5B', 'max_students': 35},
                    {'name': 'Primary 6A', 'max_students': 35},
                    {'name': 'Primary 6B', 'max_students': 35},
                ]
            }
        ]
    },
    'secondary': {
        'categories': [
            {
                'name': 'JSS',
                'section': 'jss',
                'display_order': 1,
                'classes': [
                    {'name': 'JSS 1A', 'max_students': 40},
                    {'name': 'JSS 1B', 'max_students': 40},
                    {'name': 'JSS 1C', 'max_students': 40},
                    {'name': 'JSS 2A', 'max_students': 40},
                    {'name': 'JSS 2B', 'max_students': 40},
                    {'name': 'JSS 2C', 'max_students': 40},
                    {'name': 'JSS 3A', 'max_students': 40},
                    {'name': 'JSS 3B', 'max_students': 40},
                    {'name': 'JSS 3C', 'max_students': 40},
                ]
            },
            {
                'name': 'SSS',
                'section': 'sss',
                'display_order': 2,
                'classes': [
                    {'name': 'SSS 1A', 'max_students': 40},
                    {'name': 'SSS 1B', 'max_students': 40},
                    {'name': 'SSS 1C', 'max_students': 40},
                    {'name': 'SSS 2A', 'max_students': 40},
                    {'name': 'SSS 2B', 'max_students': 40},
                    {'name': 'SSS 2C', 'max_students': 40},
                    {'name': 'SSS 3A', 'max_students': 40},
                    {'name': 'SSS 3B', 'max_students': 40},
                    {'name': 'SSS 3C', 'max_students': 40},
                ]
            }
        ]
    }
}