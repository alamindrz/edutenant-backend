# core/services.py
"""
CLEANED CORE SERVICES - Business logic extracted from models and views
NO circular imports, PROPER error handling, WELL LOGGED
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.apps import apps
from django.db.models import Q, Sum, Avg, F, Count


# SHARED IMPORTS
from shared.constants import CLASS_MODEL_PATH, StatusChoices
from shared.utils import FieldMapper
from shared.models import ClassManager

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'core'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


# ============ SERVICE EXCEPTIONS ============

class ClassManagementError(Exception):
    """Base exception for class management errors."""
    pass


class SubjectManagementError(Exception):
    """Base exception for subject management errors."""
    pass


class AcademicYearError(Exception):
    """Base exception for academic year errors."""
    pass


class TemplateServiceError(Exception):
    """Base exception for template service errors."""
    pass


# ============ CLASS MANAGEMENT SERVICES ============

class ClassManagementService:
    """
    Service for managing school classes - SINGLE SOURCE OF TRUTH.
    """

    @staticmethod
    def create_class(
        class_data: Dict[str, Any],
        school,
        created_by=None,
        auto_generate_name: bool = False
    ) -> Tuple[Any, bool]:
        """
        Create a new class with validation and related operations.

        Args:
            class_data: Class data (form cleaned_data)
            school: School instance
            created_by: User who created the class
            auto_generate_name: Whether to auto-generate class name

        Returns:
            Tuple: (class_instance, created)

        Raises:
            ClassManagementError: If class creation fails
        """
        try:
            Class = _get_model('Class')
            ClassCategory = _get_model('ClassCategory')

            # Validate and prepare data
            validated_data = ClassManagementService._validate_class_data(class_data, school)

            # Handle category
            category = validated_data.pop('category', None)
            if category and isinstance(category, int):
                category = ClassCategory.objects.get(id=category, school=school)

            if not category:
                raise ClassManagementError("Category is required for class creation")

            # Auto-generate name if requested
            if auto_generate_name and not validated_data.get('name'):
                validated_data['name'] = ClassManagementService._generate_class_name(category, school)

            # Set school and category
            validated_data['school'] = school
            validated_data['category'] = category

            # Ensure current_strength is set to 0 for new classes
            validated_data['current_strength'] = 0

            # Create class
            class_instance = Class.objects.create(**validated_data)

            # Handle post-creation operations
            ClassManagementService._handle_post_creation(class_instance, created_by)

            logger.info(f"Class created: {class_instance.name} ({class_instance.class_type})")
            return class_instance, True

        except ValidationError as e:
            logger.error(f"Class validation error: {e}")
            raise ClassManagementError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Class creation error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to create class: {str(e)}")

    @staticmethod
    def update_class(
        class_id: int,
        class_data: Dict[str, Any],
        school,
        updated_by=None
    ) -> Any:
        """
        Update class information with validation.

        Args:
            class_id: Class ID
            class_data: Updated class data
            school: School instance
            updated_by: User who updated the class

        Returns:
            Updated class instance

        Raises:
            ClassManagementError: If update fails
        """
        try:
            Class = _get_model('Class')

            class_instance = Class.objects.get(id=class_id, school=school)

            # Validate and prepare data
            validated_data = ClassManagementService._validate_class_data(
                class_data, school, class_instance=class_instance
            )

            # Handle form master changes
            new_form_master_id = validated_data.get('form_master')
            old_form_master = class_instance.form_master

            if new_form_master_id and new_form_master_id != (old_form_master.id if old_form_master else None):
                # Validate new form master belongs to same school
                Staff = _get_model('Staff', 'users')
                new_form_master = Staff.objects.get(id=new_form_master_id, school=school)
                validated_data['form_master'] = new_form_master

            # Update class
            for field, value in validated_data.items():
                if hasattr(class_instance, field):
                    setattr(class_instance, field, value)

            class_instance.save()

            # Update class strength
            class_instance.update_strength()

            # Log update
            if updated_by:
                ClassManagementService._log_class_update(class_instance, updated_by)

            logger.info(f"Class updated: {class_instance.name} by {updated_by}")
            return class_instance

        except Class.DoesNotExist:
            raise ClassManagementError(f"Class with id {class_id} not found")
        except ValidationError as e:
            logger.error(f"Class update validation error: {e}")
            raise ClassManagementError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Class update error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to update class: {str(e)}")

    @staticmethod
    def deactivate_class(class_id: int, school, deactivated_by=None) -> bool:
        """
        Deactivate a class (soft delete).

        Args:
            class_id: Class ID
            school: School instance
            deactivated_by: User who deactivated the class

        Returns:
            bool: True if successful

        Raises:
            ClassManagementError: If deactivation fails
        """
        try:
            Class = _get_model('Class')

            class_instance = Class.objects.get(id=class_id, school=school)

            # Check if class has active students
            Student = _get_model('Student', 'students')
            active_students = Student.objects.filter(
                current_class=class_instance,
                is_active=True,
                admission_status__in=['enrolled', 'accepted']
            ).exists()

            if active_students:
                raise ClassManagementError(
                    f"Cannot deactivate class '{class_instance.name}' with active students."
                )

            # Deactivate class
            class_instance.is_active = False
            class_instance.save()

            # Log deactivation
            if deactivated_by:
                ClassManagementService._log_class_deactivation(class_instance, deactivated_by)

            logger.info(f"Class deactivated: {class_instance.name} by {deactivated_by}")
            return True

        except Class.DoesNotExist:
            raise ClassManagementError(f"Class with id {class_id} not found")
        except Exception as e:
            logger.error(f"Class deactivation error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to deactivate class: {str(e)}")


    @staticmethod
    def get_class_stats(school, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get class statistics for a school.
        """
        try:
            Class = _get_model('Class')

            queryset = Class.objects.filter(school=school)

            if filters:
                # Apply filters
                if filters.get('category'):
                    queryset = queryset.filter(category_id=filters['category'])
                if filters.get('class_type'):
                    queryset = queryset.filter(class_type=filters['class_type'])
                if filters.get('is_active') is not None:
                    queryset = queryset.filter(is_active=filters['is_active'])
                if filters.get('academic_year'):
                    queryset = queryset.filter(academic_year_id=filters['academic_year'])

            total = queryset.count()
            active = queryset.filter(is_active=True).count()
            academic = queryset.filter(class_type='academic').count()
            clubs = queryset.filter(class_type='club').count()

            # Get capacity statistics
            capacity_stats = queryset.aggregate(
                total_capacity=Sum('max_students'),
                total_students=Sum('current_strength'),
                avg_capacity=Avg('max_students'),
                avg_occupancy=Avg('current_strength')
            )

            # Classes by category
            # FIXED: Now using imported Count
            categories_stats = queryset.filter(
                category__isnull=False
            ).values(
                'category__name'
            ).annotate(
                count=Count('id'),
                total_students=Sum('current_strength'),
                avg_capacity=Avg('max_students')
            )

            return {
                'total': total,
                'active': active,
                'inactive': total - active,
                'by_type': {
                    'academic': academic,
                    'clubs': clubs,
                    'other': total - academic - clubs,
                },
                'capacity_stats': capacity_stats,
                'categories_stats': list(categories_stats),
                'full_classes': queryset.filter(
                    current_strength__gte=F('max_students') # FIXED: models.F -> F
                ).count(),
                'empty_classes': queryset.filter(current_strength=0).count(),
            }

        except Exception as e:
            logger.error(f"Class stats error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to get class statistics: {str(e)}")



    @staticmethod
    def get_classes_for_teacher(teacher, school) -> List[Any]:
        """
        Get all classes assigned to a teacher.

        Args:
            teacher: Staff instance
            school: School instance

        Returns:
            List of Class instances
        """
        try:
            Class = _get_model('Class')

            # Classes where teacher is form master
            form_master_classes = Class.objects.filter(
                school=school,
                form_master=teacher,
                is_active=True
            )

            # Classes where teacher is assistant form master
            assistant_classes = Class.objects.filter(
                school=school,
                assistant_form_master=teacher,
                is_active=True
            )

            # Classes where teacher teaches subjects
            teaching_classes = Class.objects.filter(
                school=school,
                subjects_offered__teacher=teacher,
                is_active=True
            ).distinct()

            # Combine and deduplicate
            all_classes = list(form_master_classes) + list(assistant_classes) + list(teaching_classes)

            # Remove duplicates while preserving order
            seen = set()
            unique_classes = []
            for cls in all_classes:
                if cls.id not in seen:
                    seen.add(cls.id)
                    unique_classes.append(cls)

            return unique_classes

        except Exception as e:
            logger.error(f"Get teacher classes error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to get teacher classes: {str(e)}")

    # ============ PRIVATE HELPER METHODS ============

    @staticmethod
    def _validate_class_data(data: Dict[str, Any], school, class_instance=None) -> Dict[str, Any]:
        """Validate and prepare class data."""
        validated_data = FieldMapper.map_form_to_model(data, 'class')

        # Validate required fields
        required_fields = ['name', 'class_type', 'category']
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate class type
        class_type = validated_data.get('class_type')
        academic_year = validated_data.get('academic_year')

        if class_type == 'academic' and not academic_year:
            raise ValidationError({
                'academic_year': 'Academic year is required for academic classes.'
            })

        # Validate max_students
        max_students = validated_data.get('max_students')
        if max_students and max_students < 1:
            raise ValidationError({
                'max_students': 'Maximum students must be at least 1.'
            })

        # Validate form master and assistant form master
        form_master = validated_data.get('form_master')
        assistant_form_master = validated_data.get('assistant_form_master')

        if form_master and assistant_form_master and form_master == assistant_form_master:
            raise ValidationError({
                'assistant_form_master': 'Form master and assistant form master cannot be the same person.'
            })

        # Check for duplicate class name within school, type, and academic year
        if school:
            name = validated_data.get('name')
            class_type = validated_data.get('class_type')
            academic_year_id = validated_data.get('academic_year')

            if name and class_type:
                Class = _get_model('Class')
                query = Class.objects.filter(
                    school=school,
                    name=name,
                    class_type=class_type
                )

                if class_type == 'academic' and academic_year_id:
                    query = query.filter(academic_year_id=academic_year_id)
                elif class_type != 'academic':
                    query = query.filter(academic_year__isnull=True)

                if class_instance and class_instance.pk:
                    query = query.exclude(pk=class_instance.pk)

                if query.exists():
                    raise ValidationError({
                        'name': f'A {class_type} class with this name already exists.'
                    })

        return validated_data

    @staticmethod
    def _generate_class_name(category, school) -> str:
        """Generate unique class name for school."""
        # Get count of classes in this category
        Class = _get_model('Class')
        class_count = Class.objects.filter(
            school=school,
            category=category
        ).count() + 1

        # Generate name like "Primary 1A", "JSS 2B", etc.
        base_name = category.name
        section_suffix = chr(64 + class_count)  # A, B, C, ...

        return f"{base_name} {section_suffix}"

    @staticmethod
    def _handle_post_creation(class_instance, created_by):
        """Handle post-creation operations."""
        # Create default subject offerings for academic classes
        if class_instance.class_type == 'academic':
            ClassManagementService._create_default_subject_offerings(class_instance)

        # Send notifications if requested
        if created_by:
            ClassManagementService._send_class_creation_notification(class_instance, created_by)

        # Log creation
        ClassManagementService._log_class_creation(class_instance, created_by)

    @staticmethod
    def _create_default_subject_offerings(class_instance):
        """Create default subject offerings for new academic class."""
        try:
            Subject = _get_model('Subject')
            ClassSubject = _get_model('ClassSubject')

            # Get core subjects for this school level
            core_subjects = Subject.objects.filter(
                school=class_instance.school,
                category='core',
                is_active=True
            )

            for subject in core_subjects:
                ClassSubject.objects.create(
                    class_instance=class_instance,
                    subject=subject,
                    is_compulsory=True,
                    display_order=subject.display_order,
                    periods_per_week=5
                )

        except Exception as e:
            logger.warning(f"Failed to create default subject offerings for {class_instance}: {e}")

    @staticmethod
    def _send_class_creation_notification(class_instance, created_by):
        """Send notification about class creation."""
        # Placeholder for notification service integration
        # Should notify form master and relevant staff
        pass

    @staticmethod
    def _log_class_creation(class_instance, created_by):
        """Log class creation."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_class_update(class_instance, updated_by):
        """Log class update."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_class_deactivation(class_instance, deactivated_by):
        """Log class deactivation."""
        # Placeholder for audit logging
        pass


# ============ CLASS CATEGORY SERVICES ============

class ClassCategoryService:
    """
    Service for class category management.
    """

    @staticmethod
    def create_category(
        category_data: Dict[str, Any],
        school,
        created_by=None
    ) -> Tuple[Any, bool]:
        """
        Create a new class category.

        Args:
            category_data: Category data (form cleaned_data)
            school: School instance
            created_by: User who created the category

        Returns:
            Tuple: (category_instance, created)

        Raises:
            ClassManagementError: If category creation fails
        """
        try:
            ClassCategory = _get_model('ClassCategory')

            # Validate and prepare data
            validated_data = ClassCategoryService._validate_category_data(category_data)

            # Check for duplicate category name within school
            name = validated_data.get('name')
            if name and ClassCategory.objects.filter(
                school=school,
                name=name
            ).exists():
                raise ValidationError({'name': 'A category with this name already exists.'})

            # Set school
            validated_data['school'] = school

            # Create category
            category = ClassCategory.objects.create(**validated_data)

            # Log creation
            if created_by:
                ClassCategoryService._log_category_creation(category, created_by)

            logger.info(f"Class category created: {category.name}")
            return category, True

        except ValidationError as e:
            logger.error(f"Category validation error: {e}")
            raise ClassManagementError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Category creation error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to create category: {str(e)}")

    @staticmethod
    def update_category(
        category_id: int,
        category_data: Dict[str, Any],
        school,
        updated_by=None
    ) -> Any:
        """
        Update category information.

        Args:
            category_id: Category ID
            category_data: Updated category data
            school: School instance
            updated_by: User who updated the category

        Returns:
            Updated category instance

        Raises:
            ClassManagementError: If update fails
        """
        try:
            ClassCategory = _get_model('ClassCategory')

            category = ClassCategory.objects.get(id=category_id, school=school)

            # Validate and prepare data
            validated_data = ClassCategoryService._validate_category_data(
                category_data, category=category
            )

            # Update category
            for field, value in validated_data.items():
                if hasattr(category, field):
                    setattr(category, field, value)

            category.save()

            # Log update
            if updated_by:
                ClassCategoryService._log_category_update(category, updated_by)

            logger.info(f"Class category updated: {category.name} by {updated_by}")
            return category

        except ClassCategory.DoesNotExist:
            raise ClassManagementError(f"Category with id {category_id} not found")
        except ValidationError as e:
            logger.error(f"Category update validation error: {e}")
            raise ClassManagementError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Category update error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to update category: {str(e)}")

    @staticmethod
    def delete_category(category_id: int, school, deleted_by=None) -> bool:
        """
        Delete a class category if it has no classes.

        Args:
            category_id: Category ID
            school: School instance
            deleted_by: User who deleted the category

        Returns:
            bool: True if successful

        Raises:
            ClassManagementError: If deletion fails
        """
        try:
            ClassCategory = _get_model('ClassCategory')
            Class = _get_model('Class')

            category = ClassCategory.objects.get(id=category_id, school=school)

            # Check if category has classes
            if Class.objects.filter(category=category, is_active=True).exists():
                raise ClassManagementError(
                    f"Cannot delete category with active classes."
                )

            # Delete category
            category_name = category.name
            category.delete()

            # Log deletion
            if deleted_by:
                ClassCategoryService._log_category_deletion(category_name, deleted_by)

            logger.info(f"Class category deleted: {category_name} by {deleted_by}")
            return True

        except ClassCategory.DoesNotExist:
            raise ClassManagementError(f"Category with id {category_id} not found")
        except Exception as e:
            logger.error(f"Category deletion error: {e}", exc_info=True)
            raise ClassManagementError(f"Failed to delete category: {str(e)}")

    # ============ PRIVATE HELPER METHODS ============

    @staticmethod
    def _validate_category_data(data: Dict[str, Any], category=None) -> Dict[str, Any]:
        """Validate and prepare category data."""
        validated_data = data.copy()

        # Validate required fields
        required_fields = ['name', 'section']
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate display_order
        display_order = validated_data.get('display_order', 0)
        if display_order < 0:
            raise ValidationError({
                'display_order': 'Display order cannot be negative.'
            })

        return validated_data

    @staticmethod
    def _log_category_creation(category, created_by):
        """Log category creation."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_category_update(category, updated_by):
        """Log category update."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_category_deletion(category_name, deleted_by):
        """Log category deletion."""
        # Placeholder for audit logging
        pass


# ============ SUBJECT SERVICES ============

class SubjectService:
    """
    Service for subject management.
    """

    @staticmethod
    def create_subject(
        subject_data: Dict[str, Any],
        school,
        created_by=None
    ) -> Tuple[Any, bool]:
        """
        Create a new subject.

        Args:
            subject_data: Subject data (form cleaned_data)
            school: School instance
            created_by: User who created the subject

        Returns:
            Tuple: (subject_instance, created)

        Raises:
            SubjectManagementError: If subject creation fails
        """
        try:
            Subject = _get_model('Subject')

            # Validate and prepare data
            validated_data = SubjectService._validate_subject_data(subject_data, school)

            # Auto-generate code if not provided
            if not validated_data.get('code') and validated_data.get('name'):
                code = SubjectService._generate_subject_code(validated_data['name'], school)
                validated_data['code'] = code

            # Set school
            validated_data['school'] = school

            # Create subject
            subject = Subject.objects.create(**validated_data)

            # Log creation
            if created_by:
                SubjectService._log_subject_creation(subject, created_by)

            logger.info(f"Subject created: {subject.name} ({subject.code})")
            return subject, True

        except ValidationError as e:
            logger.error(f"Subject validation error: {e}")
            raise SubjectManagementError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Subject creation error: {e}", exc_info=True)
            raise SubjectManagementError(f"Failed to create subject: {str(e)}")

    @staticmethod
    def _generate_subject_code(name: str, school) -> str:
        """Generate unique subject code from name."""
        Subject = _get_model('Subject')

        # Generate base code (first 4 letters, uppercase)
        base_code = name[:4].upper().replace(' ', '')

        # Ensure uniqueness
        counter = 1
        final_code = base_code
        while Subject.objects.filter(school=school, code=final_code).exists():
            final_code = f"{base_code}{counter}"
            counter += 1

        return final_code

    @staticmethod
    def _validate_subject_data(data: Dict[str, Any], school, subject=None) -> Dict[str, Any]:
        """Validate and prepare subject data."""
        validated_data = data.copy()

        # Validate required fields
        required_fields = ['name', 'category']
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate scores
        max_score = validated_data.get('max_score', 100)
        pass_score = validated_data.get('pass_score', 40)

        if max_score <= 0:
            raise ValidationError({
                'max_score': 'Maximum score must be greater than 0.'
            })

        if pass_score < 0:
            raise ValidationError({
                'pass_score': 'Passing score cannot be negative.'
            })

        if pass_score > max_score:
            raise ValidationError({
                'pass_score': f'Passing score cannot exceed maximum score ({max_score}).'
            })

        # Validate code uniqueness within school
        code = validated_data.get('code')
        if code:
            Subject = _get_model('Subject')
            query = Subject.objects.filter(school=school, code=code)

            if subject and subject.pk:
                query = query.exclude(pk=subject.pk)

            if query.exists():
                raise ValidationError({
                    'code': 'A subject with this code already exists in this school.'
                })

        return validated_data

    @staticmethod
    def _log_subject_creation(subject, created_by):
        """Log subject creation."""
        # Placeholder for audit logging
        pass


# ============ ACADEMIC YEAR SERVICES ============

class AcademicYearService:
    """
    Service for academic year management.
    """

    @staticmethod
    def create_academic_year(
        year_data: Dict[str, Any],
        school,
        created_by=None
    ) -> Tuple[Any, bool]:
        """
        Create a new academic year.

        Args:
            year_data: Academic year data
            school: School instance
            created_by: User who created the academic year

        Returns:
            Tuple: (academic_year_instance, created)

        Raises:
            AcademicYearError: If academic year creation fails
        """
        try:
            AcademicYear = _get_model('AcademicYear')

            # Validate and prepare data
            validated_data = AcademicYearService._validate_year_data(year_data, school)

            # Check for duplicate academic year name
            name = validated_data.get('name')
            if name and AcademicYear.objects.filter(
                school=school,
                name=name
            ).exists():
                raise ValidationError({'name': 'An academic year with this name already exists.'})

            # Set school
            validated_data['school'] = school

            # If this is marked as current, deactivate other current years
            if validated_data.get('is_current'):
                AcademicYear.objects.filter(
                    school=school,
                    is_current=True
                ).update(is_current=False)

            # Create academic year
            academic_year = AcademicYear.objects.create(**validated_data)

            # Log creation
            if created_by:
                AcademicYearService._log_year_creation(academic_year, created_by)

            logger.info(f"Academic year created: {academic_year.name}")
            return academic_year, True

        except ValidationError as e:
            logger.error(f"Academic year validation error: {e}")
            raise AcademicYearError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Academic year creation error: {e}", exc_info=True)
            raise AcademicYearError(f"Failed to create academic year: {str(e)}")

    @staticmethod
    def _validate_year_data(data: Dict[str, Any], school, academic_year=None) -> Dict[str, Any]:
        """Validate and prepare academic year data."""
        validated_data = data.copy()

        # Validate required fields
        required_fields = ['name', 'start_date', 'end_date']
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate name format
        name = validated_data.get('name')
        import re
        if name and not re.match(r'^\d{4}/\d{4}$', name):
            raise ValidationError({
                'name': 'Academic year must be in format: YYYY/YYYY'
            })

        # Validate dates
        start_date = validated_data.get('start_date')
        end_date = validated_data.get('end_date')

        if start_date and end_date and start_date >= end_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })

        # Validate year matches dates
        if name and start_date and end_date:
            try:
                start_year, end_year = map(int, name.split('/'))
                if start_date.year != start_year or end_date.year != end_year:
                    raise ValidationError({
                        'name': 'Academic year dates must match the year in the name.'
                    })
            except ValueError:
                raise ValidationError({
                    'name': 'Invalid year format in name.'
                })

        return validated_data

    @staticmethod
    def _log_year_creation(academic_year, created_by):
        """Log academic year creation."""
        # Placeholder for audit logging
        pass


# ============ FACTORY FUNCTIONS ============

def get_class_management_service() -> ClassManagementService:
    """Factory function to get ClassManagementService instance."""
    return ClassManagementService()


def get_class_category_service() -> ClassCategoryService:
    """Factory function to get ClassCategoryService instance."""
    return ClassCategoryService()


def get_subject_service() -> SubjectService:
    """Factory function to get SubjectService instance."""
    return SubjectService()


def get_academic_year_service() -> AcademicYearService:
    """Factory function to get AcademicYearService instance."""
    return AcademicYearService()


# Convenient shortcuts
class_service = ClassManagementService()
category_service = ClassCategoryService()
subject_service = SubjectService()
academic_year_service = AcademicYearService()
