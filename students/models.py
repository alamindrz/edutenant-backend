# students/models.py - COMPLETELY REWRITTEN
"""
CLEANED STUDENT MODELS - Using shared architecture
NO ClassGroup references, NO circular imports, PROPER field naming
"""
import logging
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError

# SHARED IMPORTS
from shared.constants import (
    PARENT_PHONE_FIELD,
    PARENT_EMAIL_FIELD,
    STUDENT_CLASS_FIELD,
    CLASS_MODEL_PATH,
    StatusChoices
)

logger = logging.getLogger(__name__)


class EducationLevel(models.Model):
    """
    Represents educational levels within a school (Nursery, Primary, JSS, SSS).
    """
    SCHOOL_LEVELS = (
        ('nursery', 'Nursery'),
        ('primary', 'Primary School'),
        ('jss', 'Junior Secondary School'), 
        ('sss', 'Senior Secondary School'),
    )
    
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    level = models.CharField(max_length=20, choices=SCHOOL_LEVELS)
    name = models.CharField(max_length=100, help_text="Level name (e.g., 'Primary 1', 'JSS 2')")
    order = models.IntegerField(default=0, help_text="Display order within level")
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'students_education_level'
        unique_together = ['school', 'level', 'name']
        ordering = ['school', 'level', 'order']
        indexes = [
            models.Index(fields=['school', 'level']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"


# ============ KILLED: ClassGroup ============
# REMOVED: ClassGroup model - Use core.Class instead
# All ClassGroup references must be redirected to core.Class


class Parent(models.Model):
    """
    Represents a parent who can have multiple children in the school.
    """
    RELATIONSHIP_CHOICES = (
        ('parent', 'Parent'),
        ('guardian', 'Guardian'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()  # ✅ Use shared constant mapping
    phone_number = models.CharField(max_length=20)  # ✅ Use shared constant
    address = models.TextField()
    relationship = models.CharField(
        max_length=50, 
        choices=RELATIONSHIP_CHOICES, 
        default='parent'
    )
    
    # Add these fields for staff child tracking
    is_staff_child = models.BooleanField(
        default=False, 
        help_text="Is this a staff member's child?"
    )
    staff_member = models.ForeignKey(
        'users.Staff', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='children_as_parent',
        help_text="Staff member who is the parent"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students_parent'
        unique_together = ['school', 'email']
        indexes = [
            models.Index(fields=['school', 'email']),
            models.Index(fields=['school', 'phone_number']),
            models.Index(fields=['is_staff_child']),
            models.Index(fields=['staff_member']),
        ]
    
    def __str__(self):
        if self.is_staff_child and self.staff_member:
            staff_name = f"{self.staff_member.first_name} {self.staff_member.last_name}"
            return f"{self.full_name} (Staff: {staff_name}) - {self.school.name}"
        return f"{self.full_name} - {self.school.name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def children(self):
        """Get all children belonging to this parent."""
        return self.student_set.all()
    
    @property 
    def staff_children(self):
        """Get staff children (if this is a staff parent)."""
        if self.is_staff_child:
            return self.children.filter(is_staff_child=True)
        return Student.objects.none()
    
    def clean(self):
        """Validate parent data."""
        # Validate email uniqueness within school
        if self.email and Parent.objects.filter(
            school=self.school,
            email=self.email
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                'email': 'A parent with this email already exists in this school.'
            })
        
        # Validate staff child consistency
        if self.is_staff_child and not self.staff_member:
            raise ValidationError({
                'staff_member': 'Staff member must be specified for staff children.'
            })
        
        if self.staff_member and not self.is_staff_child:
            raise ValidationError({
                'is_staff_child': 'Must be marked as staff child if staff member is specified.'
            })
        
        if self.staff_member and self.staff_member.school != self.school:
            raise ValidationError({
                'staff_member': 'Staff member must be from the same school.'
            })
        
        # Validate phone number format
        if self.phone_number and not self.phone_number.startswith('+'):
            logger.warning(f"Parent {self.email}: Phone number missing country code")
    
    # ============ MOVED TO SERVICE ============
    # Removed create_user_account() method - this belongs in a service
    # Use shared services for user account creation


class Student(models.Model):
    """
    Represents a student enrolled in the school.
    Uses core.Class for academic enrollment (KILLS ClassGroup).
    """
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('U', 'Undisclosed'),
    )
    
    # Use shared StatusChoices where applicable
    ADMISSION_STATUS_CHOICES = (
        (StatusChoices.PENDING, 'Applied/Pending'),
        ('under_review', 'Under Review'), 
        (StatusChoices.APPROVED, 'Accepted'),
        (StatusChoices.REJECTED, 'Rejected'),
        ('enrolled', 'Enrolled'),
        ('graduated', 'Graduated'),
        ('withdrawn', 'Withdrawn'),
    )
    
    # Basic Information
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    admission_number = models.CharField(max_length=50, unique=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='U')
    date_of_birth = models.DateField()
    admission_status = models.CharField(
        max_length=20,
        choices=ADMISSION_STATUS_CHOICES,
        default=StatusChoices.PENDING  # ✅ Use shared constant
    )
    
    # Staff child flag
    is_staff_child = models.BooleanField(
        default=False, 
        help_text="Is this a staff member's child?"
    )

    # Application-specific fields (for pre-enrollment)
    previous_school = models.CharField(max_length=255, blank=True)
    previous_class = models.CharField(max_length=100, blank=True)
    application_notes = models.TextField(blank=True)
    
    # Parent relationship
    parent = models.ForeignKey(
        Parent, 
        on_delete=models.CASCADE, 
        related_name='students'
    )
    
    # Academic information - Use core.Class ONLY
    education_level = models.ForeignKey(
        EducationLevel, 
        on_delete=models.PROTECT, 
        related_name='students'
    )
    
    # ✅ SINGLE SOURCE OF TRUTH: core.Class for academic enrollment
    current_class = models.ForeignKey(
        CLASS_MODEL_PATH,  # ✅ Use shared constant 'core.Class'
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="Student's current academic class assignment"
    )
    
    # ✅ REMOVED: class_group field - Use core.Class instead
    # class_group = models.ForeignKey(...) - DELETED
    
    # Admission dates
    application_date = models.DateTimeField(null=True, blank=True)
    admission_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    # Medical information
    medical_conditions = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=20, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    
    # Additional info
    nationality = models.CharField(max_length=100, default='Nigerian', blank=True)
    state_of_origin = models.CharField(max_length=100, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students_student'
        verbose_name = 'Student'
        verbose_name_plural = 'Students'
        indexes = [
            models.Index(fields=['school', 'admission_number']),
            models.Index(fields=['school', 'parent']),
            models.Index(fields=['school', 'education_level']),
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'current_class']),
            models.Index(fields=['school', 'admission_status']),
            models.Index(fields=['school', 'is_staff_child']),
            models.Index(fields=['date_of_birth']),
            models.Index(fields=['first_name', 'last_name']),
        ]
        ordering = ['admission_number']
    
    def __str__(self):
        return f"{self.full_name} ({self.admission_number}) - {self.school.name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def display_name(self):
        """Formal display name."""
        title = "Master" if self.gender == 'M' else "Miss"
        return f"{title} {self.last_name}"
    
    @property
    def age(self):
        """Calculate student's current age."""
        today = timezone.now().date()
        if not self.date_of_birth:
            return None
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    @property
    def age_years_months(self):
        """Get age in years and months."""
        if not self.date_of_birth:
            return None
        
        today = timezone.now().date()
        years = today.year - self.date_of_birth.year
        months = today.month - self.date_of_birth.month
        
        if today.day < self.date_of_birth.day:
            months -= 1
        
        if months < 0:
            years -= 1
            months += 12
        
        return f"{years}y {months}m"
    
    def generate_admission_number(self):
        """Generate unique admission number if not provided."""
        if not self.admission_number:
            school_code = self.school.subdomain.upper()[:3] if self.school.subdomain else 'SCH'
            year = self.admission_date.year
            sequence = Student.objects.filter(
                school=self.school,
                admission_date__year=year
            ).count() + 1
            
            self.admission_number = f"{school_code}/{year}/{sequence:04d}"
    
    def clean(self):
        """Validate student data."""
        # Validate date of birth
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({
                'date_of_birth': 'Date of birth cannot be in the future.'
            })
        
        # Validate admission date
        if self.admission_date and self.admission_date > timezone.now().date():
            raise ValidationError({
                'admission_date': 'Admission date cannot be in the future.'
            })
        
        # Validate staff child consistency
        if self.is_staff_child:
            if not self.parent or not self.parent.is_staff_child:
                raise ValidationError({
                    'is_staff_child': 'Parent must also be marked as staff child.'
                })
        
        # Validate current class
        if self.current_class and self.current_class.school != self.school:
            raise ValidationError({
                'current_class': 'Class must be from the same school.'
            })
        
        # Validate education level
        if self.education_level and self.education_level.school != self.school:
            raise ValidationError({
                'education_level': 'Education level must be from the same school.'
            })
        
        # ✅ REMOVED: Class capacity check - this belongs in a service
        # Class capacity validation should be in ClassManager.validate_class_availability()
    
    def save(self, *args, **kwargs):
        """Save student with validation and auto-generated fields."""
        # Run validation first
        self.full_clean()
        
        # Generate admission number if needed
        if not self.admission_number:
            self.generate_admission_number()
        
        # Set application date if this is a new student
        if not self.pk and not self.application_date:
            self.application_date = timezone.now()
        
        # ✅ REMOVED: Class strength update logic - this belongs in a service
        # Class strength should be updated via signals or services
        
        # Save the student
        super().save(*args, **kwargs)
    
    # ✅ REMOVED: delete() method with class strength updates - use signals instead


class AcademicTerm(models.Model):
    """
    Represents academic terms within a session with enhanced tracking.
    """
    TERM_CHOICES = (
        ('first', 'First Term'),
        ('second', 'Second Term'), 
        ('third', 'Third Term'),
    )
    
    # Use shared StatusChoices where applicable
    TERM_STATUS = (
        ('upcoming', 'Upcoming'),
        (StatusChoices.PENDING, 'Pending'),  # ✅ Use shared constant
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        (StatusChoices.COMPLETED, 'Closed'),  # ✅ Use shared constant
        ('extended', 'Extended'),
    )
    
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    academic_year = models.CharField(max_length=20, help_text="e.g., 2024/2025")
    
    # Core dates
    start_date = models.DateField()
    end_date = models.DateField()
    actual_end_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="Actual end date if extended"
    )
    
    # Duration in weeks (flexible)
    planned_weeks = models.PositiveIntegerField(
        default=12, 
        help_text="Planned duration in weeks"
    )
    actual_weeks = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text="Actual duration in weeks"
    )
    
    # Status management
    status = models.CharField(
        max_length=15, 
        choices=TERM_STATUS, 
        default='upcoming'
    )
    is_active = models.BooleanField(default=False)
    
    # Break periods
    mid_term_break_start = models.DateField(null=True, blank=True)
    mid_term_break_end = models.DateField(null=True, blank=True)
    
    # Emergency closures
    closure_start = models.DateField(
        null=True, 
        blank=True, 
        help_text="Unexpected closure start (strike, pandemic)"
    )
    closure_end = models.DateField(
        null=True, 
        blank=True, 
        help_text="Unexpected closure end"
    )
    closure_reason = models.TextField(blank=True, help_text="Reason for closure")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'students_academic_term'
        verbose_name = 'Academic Term'
        verbose_name_plural = 'Academic Terms'
        unique_together = ['school', 'academic_year', 'term']
        ordering = ['-academic_year', 'start_date']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['academic_year']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.academic_year}"
    
    @property
    def is_current(self):
        """Check if term is currently active based on dates."""
        today = timezone.now().date()
        return self.start_date <= today <= (self.actual_end_date or self.end_date)
    
    @property
    def progress_percentage(self):
        """Calculate term progress percentage."""
        today = timezone.now().date()  # ✅ ADD THIS LINE
        
        if not self.is_current:
            return 100 if today > (self.actual_end_date or self.end_date) else 0
        
        total_days = (self.end_date - self.start_date).days
        elapsed_days = (today - self.start_date).days
        
        if total_days <= 0:
            return 0
        
        progress = min(100, int((elapsed_days / total_days) * 100))
        return progress

    
    def clean(self):
        """Validate term dates and logic."""
        # Basic date validation
        if self.start_date >= self.end_date:
            raise ValidationError("End date must be after start date.")
        
        if self.actual_end_date and self.actual_end_date < self.start_date:
            raise ValidationError("Actual end date cannot be before start date.")
        
        # Mid-term break validation
        if self.mid_term_break_start and self.mid_term_break_end:
            if self.mid_term_break_start >= self.mid_term_break_end:
                raise ValidationError("Mid-term break end must be after start.")
            if (self.mid_term_break_start < self.start_date or 
                self.mid_term_break_end > self.end_date):
                raise ValidationError("Mid-term break must be within term dates.")
        
        # Closure validation
        if self.closure_start and self.closure_end:
            if self.closure_start >= self.closure_end:
                raise ValidationError("Closure end must be after start.")
            
            # Closure should be within term dates
            if self.closure_start < self.start_date or self.closure_end > self.end_date:
                raise ValidationError("Closure must be within term dates.")
    
    def save(self, *args, **kwargs):
        """Auto-calculate weeks and handle status logic."""
        self.full_clean()  # Run validation first
        
        # Calculate planned weeks
        if self.start_date and self.end_date:
            days_diff = (self.end_date - self.start_date).days
            self.planned_weeks = max(12, days_diff // 7)
        
        # Calculate actual weeks if term ended
        if self.actual_end_date:
            days_diff = (self.actual_end_date - self.start_date).days
            self.actual_weeks = days_diff // 7
        
        # Auto-set is_active based on status and dates
        today = timezone.now().date()
        self.is_active = (
            self.status == 'active' and 
            self.start_date <= today <= (self.actual_end_date or self.end_date)
        )
        
        # Ensure only one active term per school
        if self.is_active:
            AcademicTerm.objects.filter(
                school=self.school,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        
        super().save(*args, **kwargs)


class Enrollment(models.Model):
    """
    Tracks student enrollment in academic terms.
    """
    student = models.ForeignKey(
        Student, 
        on_delete=models.CASCADE, 
        related_name='enrollments'
    )
    academic_term = models.ForeignKey(
        AcademicTerm, 
        on_delete=models.CASCADE, 
        related_name='enrollments'
    )
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    # Additional enrollment info
    enrollment_type = models.CharField(
        max_length=20,
        choices=[
            ('new', 'New Student'),
            ('continuing', 'Continuing Student'),
            ('transfer', 'Transfer Student'),
        ],
        default='continuing'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'students_enrollment'
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
        unique_together = ['student', 'academic_term']
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['academic_term', 'is_active']),
            models.Index(fields=['enrollment_type']),
        ]
    
    def __str__(self):
        return f"{self.student} - {self.academic_term}"
    
    @property
    def is_current(self):
        """Check if this enrollment is for the current term."""
        return self.academic_term.is_current


class Attendance(models.Model):
    """
    Tracks student attendance.
    """
    # Use shared StatusChoices where applicable
    ATTENDANCE_STATUS = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused Absence'),
        ('sick', 'Sick Leave'),
        ('other', 'Other'),
    )
    
    student = models.ForeignKey(
        Student, 
        on_delete=models.CASCADE, 
        related_name='attendances'
    )
    academic_term = models.ForeignKey(
        AcademicTerm, 
        on_delete=models.CASCADE, 
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10, 
        choices=ATTENDANCE_STATUS, 
        default='present'
    )
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'users.Profile', 
        on_delete=models.SET_NULL, 
        null=True
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    # Additional attendance details
    time_in = models.TimeField(null=True, blank=True, help_text="Time student arrived")
    time_out = models.TimeField(null=True, blank=True, help_text="Time student left")
    
    class Meta:
        db_table = 'students_attendance'
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
        unique_together = ['student', 'date']
        indexes = [
            models.Index(fields=['student', 'date']),
            models.Index(fields=['academic_term', 'date']),
            models.Index(fields=['status']),
            models.Index(fields=['date']),
        ]
        ordering = ['-date', 'student']
    
    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"
    
    @property
    def is_tardy(self):
        """Check if student was late."""
        return self.status == 'late'
    
    def clean(self):
        """Validate attendance data."""
        if self.time_out and self.time_in and self.time_out < self.time_in:
            raise ValidationError("Time out cannot be before time in.")
        
        # Ensure attendance date is within term dates
        if self.academic_term:
            if self.date < self.academic_term.start_date:
                raise ValidationError(
                    f"Attendance date cannot be before term start ({self.academic_term.start_date})"
                )
            term_end = self.academic_term.actual_end_date or self.academic_term.end_date
            if self.date > term_end:
                raise ValidationError(
                    f"Attendance date cannot be after term end ({term_end})"
                )


class Score(models.Model):
    """
    Tracks student scores for subjects.
    """
    ASSESSMENT_TYPES = (
        ('test', 'Test'),
        ('exam', 'Exam'),
        ('assignment', 'Assignment'),
        ('project', 'Project'),
        ('quiz', 'Quiz'),
        ('practical', 'Practical'),
    )
    
    enrollment = models.ForeignKey(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='scores'
    )
    subject = models.ForeignKey('core.Subject', on_delete=models.CASCADE)
    score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        help_text="Score out of maximum"
    )
    maximum_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=100
    )
    assessment_type = models.CharField(
        max_length=50, 
        choices=ASSESSMENT_TYPES,
        help_text="Type of assessment"
    )
    assessment_name = models.CharField(
        max_length=100, 
        blank=True,
        help_text="e.g., 'First Term Exam', 'Mid-term Test'"
    )
    assessment_date = models.DateField()
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'users.Profile', 
        on_delete=models.SET_NULL, 
        null=True
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'students_score'
        verbose_name = 'Score'
        verbose_name_plural = 'Scores'
        indexes = [
            models.Index(fields=['enrollment', 'subject']),
            models.Index(fields=['assessment_date']),
            models.Index(fields=['subject']),
            models.Index(fields=['assessment_type']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.student} - {self.subject}: {self.score}/{self.maximum_score}"
    
    @property
    def percentage(self):
        """Calculate score percentage."""
        if self.maximum_score <= 0:
            return Decimal('0.00')
        return (self.score / self.maximum_score) * 100
    
    @property
    def grade(self):
        """Calculate grade based on percentage."""
        percentage = self.percentage
        
        if percentage >= 75:
            return 'A'
        elif percentage >= 70:
            return 'AB'
        elif percentage >= 65:
            return 'B'
        elif percentage >= 60:
            return 'BC'
        elif percentage >= 55:
            return 'C'
        elif percentage >= 50:
            return 'CD'
        elif percentage >= 45:
            return 'D'
        elif percentage >= 40:
            return 'E'
        else:
            return 'F'
    
    def clean(self):
        """Validate score data."""
        if self.score < 0:
            raise ValidationError("Score cannot be negative.")
        
        if self.score > self.maximum_score:
            raise ValidationError(
                f"Score ({self.score}) cannot exceed maximum score ({self.maximum_score})"
            )
        
        if self.maximum_score <= 0:
            raise ValidationError("Maximum score must be greater than 0.") 