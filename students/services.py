# students/services.py
"""
STUDENT SERVICES - Business logic extracted from models and views
NO circular imports, PROPER error handling, WELL LOGGED
"""
import logging
import re
from typing import Optional, Tuple, List, Dict, Any
from decimal import Decimal

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils import timezone
from django.apps import apps
from django.contrib.auth import get_user_model
from django.conf import settings

# SHARED IMPORTS
from shared.constants import (
    PARENT_PHONE_FIELD,
    PARENT_EMAIL_FIELD,
    STUDENT_CLASS_FIELD,
    CLASS_MODEL_PATH,
    StatusChoices
)
from shared.utils import FieldMapper
from shared.models import ClassManager

logger = logging.getLogger(__name__)

User = get_user_model()


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'students'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


# ============ SERVICE EXCEPTIONS ============

class StudentServiceError(Exception):
    """Base exception for student service errors."""
    pass


class ParentServiceError(Exception):
    """Base exception for parent service errors."""
    pass


class ClassServiceError(Exception):
    """Base exception for class-related service errors."""
    pass


class AdmissionServiceError(Exception):
    """Base exception for admission service errors."""
    pass


# ============ STUDENT SERVICES ============

class StudentService:
    """
    Service for student-related business logic.
    """

    @staticmethod
    def create_student(
        student_data: Dict[str, Any],
        school,
        created_by=None,
        notify_parent: bool = True
    ) -> Tuple[Any, bool]:
        """
        Create a new student with validation and related operations.

        Args:
            student_data: Student data (form cleaned_data)
            school: School instance
            created_by: User who created the student
            notify_parent: Whether to send notification to parent

        Returns:
            Tuple: (student_instance, created)

        Raises:
            StudentServiceError: If student creation fails
        """
        try:
            # Get models
            Student = _get_model('Student')
            Parent = _get_model('Parent')

            # Validate and prepare data
            validated_data = StudentService._validate_student_data(student_data, school)

            # Handle parent
            parent = validated_data.pop('parent', None)
            if parent and isinstance(parent, int):
                parent = Parent.objects.get(id=parent, school=school)

            if not parent:
                raise StudentServiceError("Parent is required for student creation")

            # Check class capacity if class is specified
            current_class_id = validated_data.get('current_class_id')
            if current_class_id:
                is_available, message, class_instance = ClassManager.validate_class_availability(
                    current_class_id, school,
                    is_staff=validated_data.get('is_staff_child', False)
                )
                if not is_available:
                    raise StudentServiceError(f"Class not available: {message}")

            # Generate admission number if not provided
            if not validated_data.get('admission_number'):
                admission_number = StudentService._generate_admission_number(school)
                validated_data['admission_number'] = admission_number

            # Set school and parent
            validated_data['school'] = school
            validated_data['parent'] = parent

            # Set application date if this is a new student
            if not validated_data.get('application_date'):
                validated_data['application_date'] = timezone.now()

            # Create student
            student = Student.objects.create(**validated_data)

            # Handle post-creation operations
            StudentService._handle_post_creation(student, created_by, notify_parent)

            logger.info(f"Student created: {student.full_name} ({student.admission_number})")
            return student, True

        except ValidationError as e:
            logger.error(f"Student validation error: {e}")
            raise StudentServiceError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Student creation error: {e}", exc_info=True)
            raise StudentServiceError(f"Failed to create student: {str(e)}")

    @staticmethod
    def update_student(
        student_id: int,
        student_data: Dict[str, Any],
        school,
        updated_by=None
    ) -> Any:
        """
        Update student information with validation.

        Args:
            student_id: Student ID
            student_data: Updated student data
            school: School instance
            updated_by: User who updated the student

        Returns:
            Updated student instance

        Raises:
            StudentServiceError: If update fails
        """
        try:
            Student = _get_model('Student')

            student = Student.objects.get(id=student_id, school=school)

            # Validate and prepare data
            validated_data = StudentService._validate_student_data(
                student_data, school, student=student
            )

            # Handle class change
            new_class_id = validated_data.get('current_class_id')
            old_class_id = student.current_class_id if student.current_class else None

            if new_class_id and new_class_id != old_class_id:
                # Check new class capacity
                is_available, message, class_instance = ClassManager.validate_class_availability(
                    new_class_id, school,
                    is_staff=validated_data.get('is_staff_child', student.is_staff_child)
                )
                if not is_available:
                    raise StudentServiceError(f"Cannot change class: {message}")

            # Update student
            for field, value in validated_data.items():
                if hasattr(student, field):
                    setattr(student, field, value)

            student.save()

            # Log update
            if updated_by:
                StudentService._log_student_update(student, updated_by)

            logger.info(f"Student updated: {student.full_name} by {updated_by}")
            return student

        except Student.DoesNotExist:
            raise StudentServiceError(f"Student with id {student_id} not found")
        except ValidationError as e:
            logger.error(f"Student update validation error: {e}")
            raise StudentServiceError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Student update error: {e}", exc_info=True)
            raise StudentServiceError(f"Failed to update student: {str(e)}")

    @staticmethod
    def deactivate_student(student_id: int, school, deactivated_by=None) -> bool:
        """
        Deactivate a student (soft delete).

        Args:
            student_id: Student ID
            school: School instance
            deactivated_by: User who deactivated the student

        Returns:
            bool: True if successful

        Raises:
            StudentServiceError: If deactivation fails
        """
        try:
            Student = _get_model('Student')
            Enrollment = _get_model('Enrollment')

            student = Student.objects.get(id=student_id, school=school)

            # Deactivate student
            student.is_active = False
            student.save()

            # Deactivate current enrollment if exists
            current_enrollment = Enrollment.objects.filter(
                student=student, is_active=True
            ).first()

            if current_enrollment:
                current_enrollment.is_active = False
                current_enrollment.save()

            # Log deactivation
            if deactivated_by:
                StudentService._log_student_deactivation(student, deactivated_by)

            logger.info(f"Student deactivated: {student.full_name} by {deactivated_by}")
            return True

        except Student.DoesNotExist:
            raise StudentServiceError(f"Student with id {student_id} not found")
        except Exception as e:
            logger.error(f"Student deactivation error: {e}", exc_info=True)
            raise StudentServiceError(f"Failed to deactivate student: {str(e)}")

    @staticmethod
    def get_student_stats(school, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get student statistics for a school.

        Args:
            school: School instance
            filters: Optional filters

        Returns:
            dict: Student statistics
        """
        try:
            Student = _get_model('Student')

            queryset = Student.objects.filter(school=school)

            if filters:
                # Apply filters
                if filters.get('education_level'):
                    queryset = queryset.filter(education_level_id=filters['education_level'])
                if filters.get('current_class'):
                    queryset = queryset.filter(current_class_id=filters['current_class'])
                if filters.get('is_active') is not None:
                    queryset = queryset.filter(is_active=filters['is_active'])
                if filters.get('is_staff_child') is not None:
                    queryset = queryset.filter(is_staff_child=filters['is_staff_child'])

            total = queryset.count()
            active = queryset.filter(is_active=True).count()
            male = queryset.filter(gender='M').count()
            female = queryset.filter(gender='F').count()

            # Get by admission status
            status_counts = {}
            for status_value, status_label in Student.ADMISSION_STATUS_CHOICES:
                status_counts[status_value] = queryset.filter(
                    admission_status=status_value
                ).count()

            return {
                'total': total,
                'active': active,
                'inactive': total - active,
                'gender_distribution': {
                    'male': male,
                    'female': female,
                    'other': total - male - female,
                },
                'status_distribution': status_counts,
                'staff_children': queryset.filter(is_staff_child=True).count(),
            }

        except Exception as e:
            logger.error(f"Student stats error: {e}", exc_info=True)
            raise StudentServiceError(f"Failed to get student statistics: {str(e)}")

    # ============ PRIVATE HELPER METHODS ============

    @staticmethod
    def _validate_student_data(data: Dict[str, Any], school, student=None) -> Dict[str, Any]:
        """Validate and prepare student data."""
        validated_data = FieldMapper.map_form_to_model(data, 'student')

        # Validate required fields
        required_fields = ['first_name', 'last_name', 'parent', 'date_of_birth']
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate date of birth
        dob = validated_data.get('date_of_birth')
        if dob and dob > timezone.now().date():
            raise ValidationError({'date_of_birth': 'Date of birth cannot be in the future.'})

        # Validate admission date
        admission_date = validated_data.get('admission_date')
        if admission_date and admission_date > timezone.now().date():
            raise ValidationError({'admission_date': 'Admission date cannot be in the future.'})

        # Validate staff child consistency
        is_staff_child = validated_data.get('is_staff_child', False)
        parent_id = validated_data.get('parent')

        if is_staff_child:
            if not parent_id:
                raise ValidationError({
                    'parent': 'Parent must be specified for staff children.'
                })

            # Check if parent is marked as staff child
            Parent = _get_model('Parent')
            try:
                parent = Parent.objects.get(id=parent_id, school=school)
                if not parent.is_staff_child:
                    raise ValidationError({
                        'is_staff_child': 'Parent must also be marked as staff child.'
                    })
            except Parent.DoesNotExist:
                raise ValidationError({'parent': 'Parent not found.'})

        return validated_data

    @staticmethod
    def _generate_admission_number(school) -> str:
        """Generate unique admission number for school."""
        school_code = school.subdomain.upper()[:3] if school.subdomain else 'SCH'
        year = timezone.now().year

        Student = _get_model('Student')
        sequence = Student.objects.filter(
            school=school,
            admission_date__year=year
        ).count() + 1

        return f"{school_code}/{year}/{sequence:04d}"

    @staticmethod
    def _handle_post_creation(student, created_by, notify_parent):
        """Handle post-creation operations."""
        # Create enrollment if applicable
        if student.admission_status in ['enrolled', 'approved']:
            StudentService._create_initial_enrollment(student)

        # Send notifications if requested
        if notify_parent:
            StudentService._send_student_creation_notification(student, created_by)

        # Log creation
        StudentService._log_student_creation(student, created_by)

    @staticmethod
    def _create_initial_enrollment(student):
        """Create initial enrollment for student."""
        try:
            Enrollment = _get_model('Enrollment')
            AcademicTerm = _get_model('AcademicTerm')

            # Get current active term
            current_term = AcademicTerm.objects.filter(
                school=student.school,
                is_active=True
            ).first()

            if current_term:
                Enrollment.objects.create(
                    student=student,
                    academic_term=current_term,
                    is_active=True
                )

        except Exception as e:
            logger.warning(f"Failed to create initial enrollment for {student}: {e}")

    @staticmethod
    def _send_student_creation_notification(student, created_by):
        """Send notification about student creation."""
        # Placeholder for notification service integration
        # Should integrate with email/messaging service
        pass

    @staticmethod
    def _log_student_creation(student, created_by):
        """Log student creation."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_student_update(student, updated_by):
        """Log student update."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_student_deactivation(student, deactivated_by):
        """Log student deactivation."""
        # Placeholder for audit logging
        pass


# ============ PARENT SERVICES ============

class ParentService:
    """
    Service for parent-related business logic.
    """

    @staticmethod
    def create_parent(
        parent_data: Dict[str, Any],
        school,
        created_by=None,
        create_user_account: bool = False
    ) -> Tuple[Any, bool]:
        """
        Create a new parent with validation.

        Args:
            parent_data: Parent data (form cleaned_data)
            school: School instance
            created_by: User who created the parent
            create_user_account: Whether to create user account

        Returns:
            Tuple: (parent_instance, created)

        Raises:
            ParentServiceError: If parent creation fails
        """
        try:
            Parent = _get_model('Parent')

            # Validate and prepare data
            validated_data = ParentService._validate_parent_data(parent_data, school)

            # Check for duplicate email
            email = validated_data.get(PARENT_EMAIL_FIELD)
            if email and Parent.objects.filter(
                school=school,
                email=email
            ).exists():
                raise ValidationError({'email': 'A parent with this email already exists.'})

            # Set school
            validated_data['school'] = school

            # Create parent
            parent = Parent.objects.create(**validated_data)

            # Create user account if requested
            if create_user_account:
                ParentService.create_parent_user_account(parent, created_by)

            # Log creation
            if created_by:
                ParentService._log_parent_creation(parent, created_by)

            logger.info(f"Parent created: {parent.full_name} ({parent.email})")
            return parent, True

        except ValidationError as e:
            logger.error(f"Parent validation error: {e}")
            raise ParentServiceError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Parent creation error: {e}", exc_info=True)
            raise ParentServiceError(f"Failed to create parent: {str(e)}")

    @staticmethod
    def update_parent(
        parent_id: int,
        parent_data: Dict[str, Any],
        school,
        updated_by=None
    ) -> Any:
        """
        Update parent information.

        Args:
            parent_id: Parent ID
            parent_data: Updated parent data
            school: School instance
            updated_by: User who updated the parent

        Returns:
            Updated parent instance

        Raises:
            ParentServiceError: If update fails
        """
        try:
            Parent = _get_model('Parent')

            parent = Parent.objects.get(id=parent_id, school=school)

            # Validate and prepare data
            validated_data = ParentService._validate_parent_data(
                parent_data, school, parent=parent
            )

            # Update parent
            for field, value in validated_data.items():
                if hasattr(parent, field):
                    setattr(parent, field, value)

            parent.save()

            # Log update
            if updated_by:
                ParentService._log_parent_update(parent, updated_by)

            logger.info(f"Parent updated: {parent.full_name} by {updated_by}")
            return parent

        except Parent.DoesNotExist:
            raise ParentServiceError(f"Parent with id {parent_id} not found")
        except ValidationError as e:
            logger.error(f"Parent update validation error: {e}")
            raise ParentServiceError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Parent update error: {e}", exc_info=True)
            raise ParentServiceError(f"Failed to update parent: {str(e)}")

    @staticmethod
    def delete_parent(parent_id: int, school, deleted_by=None) -> bool:
        """
        Delete a parent if they have no children.

        Args:
            parent_id: Parent ID
            school: School instance
            deleted_by: User who deleted the parent

        Returns:
            bool: True if successful

        Raises:
            ParentServiceError: If deletion fails
        """
        try:
            Parent = _get_model('Parent')

            parent = Parent.objects.get(id=parent_id, school=school)

            # Check if parent has children
            if parent.children.count() > 0:
                raise ParentServiceError(
                    f"Cannot delete parent with {parent.children.count()} children."
                )

            # Delete parent
            parent_name = parent.full_name
            parent.delete()

            # Log deletion
            if deleted_by:
                ParentService._log_parent_deletion(parent_name, deleted_by)

            logger.info(f"Parent deleted: {parent_name} by {deleted_by}")
            return True

        except Parent.DoesNotExist:
            raise ParentServiceError(f"Parent with id {parent_id} not found")
        except Exception as e:
            logger.error(f"Parent deletion error: {e}", exc_info=True)
            raise ParentServiceError(f"Failed to delete parent: {str(e)}")

    @staticmethod
    def create_parent_user_account(parent, created_by=None) -> Optional[User]:
        """
        Create user account for parent.

        Args:
            parent: Parent instance
            created_by: User who created the account

        Returns:
            User instance if created, None otherwise
        """
        try:
            # Check if parent already has user account
            if parent.user:
                logger.warning(f"Parent {parent.email} already has user account")
                return parent.user

            # Create user
            username = f"parent_{parent.school.subdomain}_{parent.email}"
            password = User.objects.make_random_password()

            user = User.objects.create_user(
                username=username,
                email=parent.email,
                password=password,
                first_name=parent.first_name,
                last_name=parent.last_name,
                phone_number=getattr(parent, PARENT_PHONE_FIELD, '')
            )

            # Update parent with user reference
            parent.user = user
            parent.save()

            # Create profile for parent
            ParentService._create_parent_profile(parent, user)

            # Send welcome email with credentials
            ParentService._send_welcome_email(parent, user, password)

            logger.info(f"User account created for parent: {parent.email}")
            return user

        except Exception as e:
            logger.error(f"Parent user account creation error: {e}", exc_info=True)
            raise ParentServiceError(f"Failed to create user account: {str(e)}")

    @staticmethod
    def get_parent_stats(school, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get parent statistics for a school.

        Args:
            school: School instance
            filters: Optional filters

        Returns:
            dict: Parent statistics
        """
        try:
            Parent = _get_model('Parent')
            Student = _get_model('Student')

            parents = Parent.objects.filter(school=school)

            total_parents = parents.count()
            parents_with_accounts = parents.filter(user__isnull=False).count()
            staff_parents = parents.filter(is_staff_child=True).count()

            # Get children statistics
            children_per_parent = []
            for parent in parents:
                children_count = parent.children.count()
                children_per_parent.append(children_count)

            avg_children = sum(children_per_parent) / len(children_per_parent) if children_per_parent else 0

            return {
                'total_parents': total_parents,
                'parents_with_accounts': parents_with_accounts,
                'parents_without_accounts': total_parents - parents_with_accounts,
                'staff_parents': staff_parents,
                'average_children_per_parent': round(avg_children, 1),
                'max_children': max(children_per_parent) if children_per_parent else 0,
                'min_children': min(children_per_parent) if children_per_parent else 0,
            }

        except Exception as e:
            logger.error(f"Parent stats error: {e}", exc_info=True)
            raise ParentServiceError(f"Failed to get parent statistics: {str(e)}")

    # ============ PRIVATE HELPER METHODS ============

    @staticmethod
    def _validate_parent_data(data: Dict[str, Any], school, parent=None) -> Dict[str, Any]:
        """Validate and prepare parent data."""
        validated_data = FieldMapper.map_form_to_model(data, 'parent')

        # Validate required fields
        required_fields = ['first_name', 'last_name', PARENT_EMAIL_FIELD]
        for field in required_fields:
            if field not in validated_data or not validated_data[field]:
                raise ValidationError({field: "This field is required"})

        # Validate email format
        email = validated_data.get(PARENT_EMAIL_FIELD)
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            raise ValidationError({PARENT_EMAIL_FIELD: 'Enter a valid email address.'})

        # Validate staff child consistency
        is_staff_child = validated_data.get('is_staff_child', False)
        staff_member = validated_data.get('staff_member')

        if is_staff_child and not staff_member:
            raise ValidationError({
                'staff_member': 'Staff member must be specified for staff children.'
            })

        if staff_member and not is_staff_child:
            raise ValidationError({
                'is_staff_child': 'Must be marked as staff child if staff member is specified.'
            })

        # Validate phone number
        phone = validated_data.get(PARENT_PHONE_FIELD)
        if phone:
            # Basic phone validation for Nigeria
            digits = ''.join(filter(str.isdigit, str(phone)))
            if len(digits) < 10:
                raise ValidationError({
                    PARENT_PHONE_FIELD: 'Enter a valid phone number.'
                })

        return validated_data

    @staticmethod
    def _create_parent_profile(parent, user):
        """Create profile for parent."""
        try:
            Profile = _get_model('Profile', 'users')
            Role = _get_model('Role', 'users')

            # Get parent role for this school
            parent_role = Role.objects.filter(
                school=parent.school,
                system_role_type='parent'
            ).first()

            if parent_role:
                Profile.objects.create(
                    user=user,
                    school=parent.school,
                    role=parent_role,
                    parent_profile=parent
                )

        except Exception as e:
            logger.warning(f"Failed to create parent profile: {e}")

    @staticmethod
    def _send_welcome_email(parent, user, password):
        """Send welcome email to parent."""
        # Placeholder for email service integration
        # Should send email with login credentials
        pass

    @staticmethod
    def _log_parent_creation(parent, created_by):
        """Log parent creation."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_parent_update(parent, updated_by):
        """Log parent update."""
        # Placeholder for audit logging
        pass

    @staticmethod
    def _log_parent_deletion(parent_name, deleted_by):
        """Log parent deletion."""
        # Placeholder for audit logging
        pass

# ============ ENROLLMENT SERVICES ============

class EnrollmentService:
    """
    Service for enrollment-related business logic.
    """

    @staticmethod
    def enroll_student(
        student_id: int,
        academic_term_id: int,
        enrollment_type: str = 'continuing',
        notes: str = '',
        enrolled_by=None
    ) -> Any:
        """
        Enroll student in academic term.

        Args:
            student_id: Student ID
            academic_term_id: AcademicTerm ID
            enrollment_type: Type of enrollment
            notes: Enrollment notes
            enrolled_by: User who enrolled the student

        Returns:
            Enrollment instance

        Raises:
            AdmissionServiceError: If enrollment fails
        """
        try:
            Student = _get_model('Student')
            AcademicTerm = _get_model('AcademicTerm')
            Enrollment = _get_model('Enrollment')

            student = Student.objects.get(id=student_id)
            academic_term = AcademicTerm.objects.get(id=academic_term_id)

            # Check if student is already enrolled
            existing_enrollment = Enrollment.objects.filter(
                student=student,
                academic_term=academic_term
            ).first()

            if existing_enrollment:
                if existing_enrollment.is_active:
                    raise AdmissionServiceError(
                        f"Student {student.full_name} is already enrolled in {academic_term.name}"
                    )
                else:
                    # Reactivate existing enrollment
                    existing_enrollment.is_active = True
                    existing_enrollment.enrollment_type = enrollment_type
                    existing_enrollment.notes = notes
                    existing_enrollment.save()
                    return existing_enrollment

            # Create new enrollment
            enrollment = Enrollment.objects.create(
                student=student,
                academic_term=academic_term,
                enrollment_type=enrollment_type,
                notes=notes,
                is_active=True
            )

            # Log enrollment
            if enrolled_by:
                EnrollmentService._log_enrollment(enrollment, enrolled_by)

            logger.info(
                f"Student {student.full_name} enrolled in {academic_term.name} by {enrolled_by}"
            )
            return enrollment

        except Student.DoesNotExist:
            raise AdmissionServiceError(f"Student with id {student_id} not found")
        except AcademicTerm.DoesNotExist:
            raise AdmissionServiceError(f"Academic term with id {academic_term_id} not found")
        except Exception as e:
            logger.error(f"Enrollment error: {e}", exc_info=True)
            raise AdmissionServiceError(f"Failed to enroll student: {str(e)}")

    @staticmethod
    def get_active_enrollments(school, academic_term_id=None) -> List[Any]:
        """
        Get active enrollments for a school.

        Args:
            school: School instance
            academic_term_id: Optional academic term filter

        Returns:
            List of Enrollment instances
        """
        try:
            Enrollment = _get_model('Enrollment')
            AcademicTerm = _get_model('AcademicTerm')

            if academic_term_id:
                academic_term = AcademicTerm.objects.get(id=academic_term_id, school=school)
                enrollments = Enrollment.objects.filter(
                    student__school=school,
                    academic_term=academic_term,
                    is_active=True
                ).select_related('student', 'academic_term')
            else:
                enrollments = Enrollment.objects.filter(
                    student__school=school,
                    is_active=True
                ).select_related('student', 'academic_term')

            return list(enrollments)

        except Exception as e:
            logger.error(f"Get enrollments error: {e}", exc_info=True)
            raise AdmissionServiceError(f"Failed to get enrollments: {str(e)}")

    @staticmethod
    def _log_enrollment(enrollment, enrolled_by):
        """Log enrollment."""
        # Placeholder for audit logging
        pass


# ============ ATTENDANCE SERVICES ============

class AttendanceService:
    """
    Service for attendance-related business logic.
    """

    @staticmethod
    def record_attendance(
        student_id: int,
        academic_term_id: int,
        date,
        status: str = 'present',
        time_in=None,
        time_out=None,
        remarks: str = '',
        recorded_by=None
    ) -> Any:
        """
        Record student attendance.

        Args:
            student_id: Student ID
            academic_term_id: AcademicTerm ID
            date: Attendance date
            status: Attendance status
            time_in: Time student arrived
            time_out: Time student left
            remarks: Additional remarks
            recorded_by: User who recorded attendance

        Returns:
            Attendance instance

        Raises:
            AdmissionServiceError: If attendance recording fails
        """
        try:
            Student = _get_model('Student')
            AcademicTerm = _get_model('AcademicTerm')
            Attendance = _get_model('Attendance')

            student = Student.objects.get(id=student_id)
            academic_term = AcademicTerm.objects.get(id=academic_term_id)

            # Check if attendance already recorded for this date
            existing_attendance = Attendance.objects.filter(
                student=student,
                date=date
            ).first()

            if existing_attendance:
                # Update existing attendance
                existing_attendance.status = status
                existing_attendance.time_in = time_in
                existing_attendance.time_out = time_out
                existing_attendance.remarks = remarks
                existing_attendance.recorded_by = recorded_by
                existing_attendance.save()
                return existing_attendance

            # Create new attendance record
            attendance = Attendance.objects.create(
                student=student,
                academic_term=academic_term,
                date=date,
                status=status,
                time_in=time_in,
                time_out=time_out,
                remarks=remarks,
                recorded_by=recorded_by
            )

            logger.info(
                f"Attendance recorded for {student.full_name} on {date}: {status}"
            )
            return attendance

        except Student.DoesNotExist:
            raise AdmissionServiceError(f"Student with id {student_id} not found")
        except AcademicTerm.DoesNotExist:
            raise AdmissionServiceError(f"Academic term with id {academic_term_id} not found")
        except Exception as e:
            logger.error(f"Attendance recording error: {e}", exc_info=True)
            raise AdmissionServiceError(f"Failed to record attendance: {str(e)}")

    @staticmethod
    def get_attendance_stats(
        student_id: int = None,
        class_id: int = None,
        academic_term_id: int = None,
        start_date=None,
        end_date=None
    ) -> Dict[str, Any]:
        """
        Get attendance statistics.

        Args:
            student_id: Optional student filter
            class_id: Optional class filter
            academic_term_id: Optional academic term filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            dict: Attendance statistics
        """
        try:
            Attendance = _get_model('Attendance')

            queryset = Attendance.objects.all()

            # Apply filters
            if student_id:
                queryset = queryset.filter(student_id=student_id)

            if class_id:
                queryset = queryset.filter(student__current_class_id=class_id)

            if academic_term_id:
                queryset = queryset.filter(academic_term_id=academic_term_id)

            if start_date:
                queryset = queryset.filter(date__gte=start_date)

            if end_date:
                queryset = queryset.filter(date__lte=end_date)

            # Calculate statistics
            total_records = queryset.count()

            status_counts = {}
            for status_value, status_label in Attendance.ATTENDANCE_STATUS:
                status_counts[status_value] = queryset.filter(
                    status=status_value
                ).count()

            attendance_rate = 0
            if total_records > 0:
                present_count = status_counts.get('present', 0)
                attendance_rate = (present_count / total_records) * 100

            return {
                'total_records': total_records,
                'status_counts': status_counts,
                'attendance_rate': round(attendance_rate, 2),
                'late_count': status_counts.get('late', 0),
                'absent_count': status_counts.get('absent', 0),
            }

        except Exception as e:
            logger.error(f"Attendance stats error: {e}", exc_info=True)
            raise AdmissionServiceError(f"Failed to get attendance statistics: {str(e)}")


# ============ FACTORY FUNCTIONS ============

def get_student_service() -> StudentService:
    """Factory function to get StudentService instance."""
    return StudentService()


def get_parent_service() -> ParentService:
    """Factory function to get ParentService instance."""
    return ParentService()


def get_enrollment_service() -> EnrollmentService:
    """Factory function to get EnrollmentService instance."""
    return EnrollmentService()


def get_attendance_service() -> AttendanceService:
    """Factory function to get AttendanceService instance."""
    return AttendanceService()


# Convenient shortcuts
student_service = StudentService()
parent_service = ParentService()
enrollment_service = EnrollmentService()
attendance_service = AttendanceService()
