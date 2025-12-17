# core/models.py
"""
CLEANED CORE MODELS - Using shared architecture
Consistent field naming, proper relationships, well documented
"""
import logging
from decimal import Decimal
from typing import Optional, List

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError

# SHARED IMPORTS
from shared.constants import StatusChoices

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str):
    """Get model lazily to avoid circular imports."""
    try:
        from django.apps import apps
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


# ============ SCHOOL MODEL ============

class School(models.Model):
    """School institution model - foundation for multi-tenancy."""
    SUBDOMAIN_STATUS = (
        ('none', 'No Subdomain'),
        ('pending', 'Pending Payment'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
    )
    
    SCHOOL_TYPES = (
        ('nursery', 'Nursery Only'),
        ('primary', 'Primary Only'), 
        ('secondary', 'Secondary Only'),
        ('combined', 'Nursery & Primary'),
        ('full', 'Full K-12'),
    )
    
    # Basic Information
    name = models.CharField(max_length=255, help_text="Official school name")
    subdomain = models.SlugField(
        unique=True, 
        blank=True, 
        null=True, 
        help_text="Optional custom subdomain"
    )
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPES, default='primary')
    contact_email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # White-label Branding
    logo = models.ImageField(upload_to='school_logos/', null=True, blank=True)
    primary_color = models.CharField(max_length=7, default='#3B82F6')
    secondary_color = models.CharField(max_length=7, default='#1E40AF')
    footer_text = models.TextField(blank=True, default='')
    hide_platform_branding = models.BooleanField(default=True)
    
    # Payment Configuration
    paystack_subaccount_id = models.CharField(max_length=128, blank=True, null=True)
    platform_commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.015'))
    bank_code = models.CharField(max_length=10, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    account_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Subscription Management - SIMPLIFIED
    subdomain_status = models.CharField(max_length=20, choices=SUBDOMAIN_STATUS, default='none')
    subdomain_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Onboarding
    onboarding_completed = models.BooleanField(default=False)
    onboarding_step = models.IntegerField(default=0)
    
    # Operational
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Fee Policies Configuration
    fee_policies = models.JSONField(default=dict, blank=True, help_text="School fee policies configuration")
    
    # Application Fee Policies
    application_fee_required = models.BooleanField(default=True)
    application_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    application_fee_currency = models.CharField(max_length=3, default='NGN')
    
    # Staff Children Policies
    staff_children_waive_application_fee = models.BooleanField(default=False)
    staff_children_discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0'),
        help_text="Percentage discount on school fees for staff children"
    )
    staff_children_max_discount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0'),
        help_text="Maximum discount amount (0 = unlimited)"
    )
    
    # Scholarship Policies
    scholarship_enabled = models.BooleanField(default=False)
    scholarship_application_required = models.BooleanField(default=False)
    scholarship_max_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('100'),
        help_text="Maximum scholarship percentage"
    )
    
    # Payment Methods
    allowed_payment_methods = models.JSONField(
        default=list,
        blank=True,
        help_text="['bank_transfer', 'paystack', 'cash', 'cheque']"
    )
    
    # Application Form Policies
    application_form_enabled = models.BooleanField(default=True)
    allow_staff_applications = models.BooleanField(default=True)
    allow_external_applications = models.BooleanField(default=True)
    
    # Timelines
    application_deadline_extension_days = models.PositiveIntegerField(
        default=7,
        help_text="Grace period after deadline for special cases"
    )
    
    class Meta:
        db_table = 'schools_school'
        indexes = [
            models.Index(fields=['subdomain', 'is_active']),
            models.Index(fields=['subdomain_status', 'subdomain_expires_at']),
            models.Index(fields=['name']),
            models.Index(fields=['contact_email']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.subdomain or 'no-subdomain'})"
    
    @property
    def is_subdomain_active(self) -> bool:
        """Check if school has an active subdomain."""
        return (
            self.subdomain_status == 'active' and 
            self.subdomain and
            self.subdomain_expires_at and 
            self.subdomain_expires_at > timezone.now()
        )
    
    @property
    def school_url(self) -> str:
        """Get school URL - either subdomain or path-based."""
        if self.is_subdomain_active:
            return f"https://{self.subdomain}.edusuite.com"
        else:
            return f"/schools/{self.id}/"
    
    def get_open_application_forms(self):
        """Get active AND open application forms for admission into this school."""
        try:
            ApplicationForm = _get_model('ApplicationForm', 'admissions')
            now = timezone.now()
            
            return ApplicationForm.objects.filter(
                school=self,
                status='active',
                open_date__lte=now,
                close_date__gte=now
            )
        except LookupError:
            logger.warning(f"ApplicationForm model not found")
            return None
    
    @property
    def is_accepting_applications(self) -> bool:
        """Check if school is accepting any applications."""
        try:
            forms = self.get_open_application_forms()
            return forms.exists() if forms else False and self.application_form_enabled
        except Exception:
            return False
    
    def get_staff_children_discount(self, fee_amount: Decimal) -> Decimal:
        """Calculate discount for staff children."""
        if self.staff_children_discount_percentage <= Decimal('0'):
            return Decimal('0')
        
        discount = fee_amount * (self.staff_children_discount_percentage / Decimal('100'))
        
        if self.staff_children_max_discount > Decimal('0'):
            discount = min(discount, self.staff_children_max_discount)
        
        return discount.quantize(Decimal('0.01'))
    
    def get_open_positions(self):
        """Get open teaching positions that are actively hiring."""
        try:
            OpenPosition = _get_model('OpenPosition', 'users')
            return OpenPosition.objects.filter(school=self, is_active=True)
        except LookupError:
            logger.warning(f"OpenPosition model not found")
            return None
    
    def get_open_positions_list(self) -> List[str]:
        """Get list of open teaching positions for display."""
        try:
            OpenPosition = _get_model('OpenPosition', 'users')
            return list(OpenPosition.objects.filter(
                school=self,
                is_active=True
            ).values_list('title', flat=True))
        except LookupError:
            return []
    
    def add_open_position(self, title: str, department: str = "", description: str = "", requirements: str = ""):
        """Add a new open teaching position."""
        try:
            OpenPosition = _get_model('OpenPosition', 'users')
            return OpenPosition.objects.create(
                school=self,
                title=title,
                department=department,
                description=description,
                requirements=requirements
            )
        except LookupError as e:
            logger.error(f"Cannot add open position: {e}")
            return None
    
    @property
    def open_application_forms_count(self) -> int:
        """Count of active application forms."""
        forms = self.get_open_application_forms()
        return forms.count() if forms else 0
    
    def clean(self):
        """Validate school data."""
        # Validate subdomain uniqueness (except for null/empty)
        if self.subdomain:
            if School.objects.filter(
                subdomain=self.subdomain
            ).exclude(pk=self.pk).exists():
                raise ValidationError({'subdomain': 'This subdomain is already in use.'})
        
        # Validate subdomain status consistency
        if self.subdomain_status == 'active' and not self.subdomain:
            raise ValidationError({
                'subdomain': 'Active subdomain status requires a subdomain.'
            })
        
        # Validate commission rate
        if self.platform_commission_rate < Decimal('0') or self.platform_commission_rate > Decimal('1'):
            raise ValidationError({
                'platform_commission_rate': 'Commission rate must be between 0 and 1.'
            })
    
    def save(self, *args, **kwargs):
        """Save with validation."""
        self.full_clean()
        super().save(*args, **kwargs)


# ============ CLASS CATEGORY MODEL ============

class ClassCategory(models.Model):
    """Category for grouping classes (e.g., Primary, Secondary, JSS, SSS)"""
    SCHOOL_SECTIONS = (
        ('nursery', 'Nursery'),
        ('primary', 'Primary'),
        ('jss', 'Junior Secondary'),
        ('sss', 'Senior Secondary'),
        ('special', 'Special Needs'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='class_categories')
    name = models.CharField(max_length=100)
    section = models.CharField(max_length=20, choices=SCHOOL_SECTIONS)
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'core_class_category'
        unique_together = ['school', 'name']
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['section']),
        ]
        verbose_name = 'Class Category'
        verbose_name_plural = 'Class Categories'
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    def get_classes(self):
        """Get all active classes in this category."""
        return self.classes.filter(is_active=True)
    
    def clean(self):
        """Validate category data."""
        if not self.school:
            raise ValidationError({'school': 'School is required.'})


# ============ ACADEMIC YEAR MODEL ============

class AcademicYear(models.Model):
    """Academic year model for organizing school years."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='academic_years')
    name = models.CharField(max_length=50, help_text="e.g., 2024/2025")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'core_academic_year'
        unique_together = ['school', 'name']
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['school', 'is_current']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        verbose_name = 'Academic Year'
        verbose_name_plural = 'Academic Years'
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    @property
    def is_current_year(self) -> bool:
        """Check if this is the current academic year."""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date
    
    @property
    def duration_months(self) -> int:
        """Get duration of academic year in months."""
        if self.start_date and self.end_date:
            return (self.end_date.year - self.start_date.year) * 12 + self.end_date.month - self.start_date.month
        return 0
    
    def get_classes(self):
        """Get all classes for this academic year."""
        return self.class_set.filter(is_active=True, class_type='academic')
    
    def clean(self):
        """Validate academic year dates."""
        if self.start_date >= self.end_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})
        
        # Ensure only one current academic year per school
        if self.is_current:
            AcademicYear.objects.filter(
                school=self.school,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)


# ============ CLASS MODEL (MAIN) ============

class Class(models.Model):
    """
    Main Academic Class Model - SINGLE SOURCE OF TRUTH for class assignments
    """
    CLASS_TYPES = [
        ('academic', 'Academic Class'),
        ('stream', 'Stream/Group'),
        ('club', 'Club/Activity'),
        ('tutorial', 'Tutorial Group'),
    ]
    
    # Core information
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='classes')
    name = models.CharField(max_length=100)
    class_type = models.CharField(max_length=20, choices=CLASS_TYPES, default='academic')
    category = models.ForeignKey(
        ClassCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='classes'
    )
    education_level = models.ForeignKey(
        'students.EducationLevel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='classes',
        help_text="Education level for this class"
    )
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True, 
        blank=True  # Optional for non-academic groups
    )
    
    # Class management
    form_master = models.ForeignKey(
        'users.Staff',
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='form_master_classes',
        help_text="Teacher responsible for this class"
    )
    assistant_form_master = models.ForeignKey(
        'users.Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assistant_form_master_classes',
        help_text="Assistant form master"
    )
    
    # Class configuration
    max_students = models.IntegerField(default=40)
    current_strength = models.IntegerField(default=0, editable=False)
    room_number = models.CharField(max_length=20, blank=True)
    
    # Academic information
    is_graduated = models.BooleanField(default=False)
    graduation_date = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_class'
        unique_together = ('name', 'school', 'academic_year', 'class_type')
        ordering = ['category__display_order', 'name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['form_master', 'is_active']),
            models.Index(fields=['academic_year', 'class_type']),
            models.Index(fields=['school', 'academic_year']),
            models.Index(fields=['education_level']),
            models.Index(fields=['name']),
        ]
        verbose_name = "Class"
        verbose_name_plural = "Classes"
    
    def __str__(self):
        academic_year_str = f" - {self.academic_year.name}" if self.academic_year else ""
        return f"{self.name}{academic_year_str} - {self.school.name}"
    
    @property
    def full_name(self) -> str:
        """Get full display name of class."""
        if self.category:
            return f"{self.category.name} - {self.name}"
        return self.name
    
    @property
    def capacity_percentage(self) -> float:
        """Get class capacity percentage."""
        if self.max_students == 0:
            return 0.0
        return round((self.current_strength / self.max_students) * 100, 1)
    
    @property
    def is_full(self) -> bool:
        """Check if class is at full capacity."""
        return self.current_strength >= self.max_students
    
    @property
    def available_seats(self) -> int:
        """Get number of available seats."""
        return max(0, self.max_students - self.current_strength)
    
    def get_students(self):
        """Get all active students in this class."""
        try:
            Student = _get_model('Student', 'students')
            return Student.objects.filter(
                current_class=self,
                is_active=True,
                admission_status='enrolled'
            ).select_related('parent')
        except LookupError:
            return None
    
    def get_student_list(self):
        """Get student list for display."""
        students = self.get_students()
        if students:
            return students.order_by('first_name', 'last_name')
        return []
    
    def update_strength(self):
        """Update current student count from related students."""
        try:
            Student = _get_model('Student', 'students')
            self.current_strength = Student.objects.filter(
                current_class=self,
                is_active=True,
                admission_status__in=['enrolled', 'accepted']
            ).count()
            if self.pk:  # Don't save if object hasn't been saved yet
                self.save(update_fields=['current_strength'])
        except LookupError:
            logger.error(f"Cannot update class strength: Student model not found")
    
    def can_add_student(self) -> bool:
        """Check if class can accept more students."""
        return self.current_strength < self.max_students
    
    def clean(self):
        """Validate class data."""
        # Ensure academic_year is required for academic classes
        if self.class_type == 'academic' and not self.academic_year:
            raise ValidationError({
                'academic_year': 'Academic year is required for academic classes.'
            })
        
        # Validate max_students
        if self.max_students <= 0:
            raise ValidationError({
                'max_students': 'Maximum students must be greater than 0.'
            })
        
        # Ensure current_strength doesn't exceed max_students
        if self.current_strength > self.max_students:
            raise ValidationError({
                'current_strength': f'Current strength ({self.current_strength}) exceeds maximum capacity ({self.max_students}).'
            })
        
        # Ensure form_master and assistant are from same school
        if self.form_master and self.form_master.school != self.school:
            raise ValidationError({
                'form_master': 'Form master must be from the same school.'
            })
        
        if self.assistant_form_master and self.assistant_form_master.school != self.school:
            raise ValidationError({
                'assistant_form_master': 'Assistant form master must be from the same school.'
            })
        
        # Validate education level belongs to same school
        if self.education_level and self.education_level.school != self.school:
            raise ValidationError({
                'education_level': 'Education level must be from the same school.'
            })
    
    def save(self, *args, **kwargs):
        """Save class with validation and post-save logic."""
        self.full_clean()  # Run validation first
        
        # If this is a new academic class, create default subject offerings
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and self.class_type == 'academic':
            self._create_default_subject_offerings()
    
    def _create_default_subject_offerings(self):
        """Create default subject offerings for new academic class."""
        try:
            Subject = _get_model('Subject', 'core')
            ClassSubject = _get_model('ClassSubject', 'core')
            
            # Get core subjects for this school level
            core_subjects = Subject.objects.filter(
                school=self.school,
                category='core',
                is_active=True
            )
            
            for subject in core_subjects:
                ClassSubject.objects.create(
                    class_instance=self,
                    subject=subject,
                    is_compulsory=True,
                    display_order=subject.display_order
                )
        except LookupError:
            logger.warning(f"Cannot create default subject offerings: models not found")


# ============ CLASS MONITOR MODEL ============

class ClassMonitor(models.Model):
    """Student monitors for each class"""
    MONITOR_ROLES = (
        ('head', 'Head Monitor'),
        ('assistant', 'Assistant Monitor'),
        ('prefect', 'Prefect'),
        ('captain', 'Captain'),
        ('secretary', 'Secretary'),
        ('treasurer', 'Treasurer'),
    )
    
    class_instance = models.ForeignKey(
        Class, 
        on_delete=models.CASCADE, 
        related_name="monitors"
    )
    student = models.ForeignKey(
        'students.Student', 
        on_delete=models.CASCADE, 
        related_name="monitor_positions"
    )
    role = models.CharField(max_length=20, choices=MONITOR_ROLES)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Responsibilities
    responsibilities = models.TextField(help_text="List of monitor responsibilities")
    position = models.CharField(max_length=100)
    
    # Audit
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'core_class_monitor'
        unique_together = ['class_instance', 'student', 'role']
        ordering = ['class_instance', 'role', 'start_date']
        indexes = [
            models.Index(fields=['class_instance', 'is_active']),
            models.Index(fields=['student', 'is_active']),
        ]
        verbose_name = 'Class Monitor'
        verbose_name_plural = 'Class Monitors'
    
    def __str__(self):
        return f"{self.student.full_name} - {self.get_role_display()} of {self.class_instance.name}"
    
    @property
    def duration_days(self) -> int:
        """Get duration in days."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        if self.start_date:
            return (timezone.now().date() - self.start_date).days
        return 0
    
    def is_current(self) -> bool:
        """Check if this monitor assignment is current."""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return True
    
    def clean(self):
        """Validate monitor assignment."""
        # Ensure student belongs to the same class
        if self.student.current_class != self.class_instance:
            raise ValidationError({
                'student': 'Student must be a member of this class.'
            })
        
        # Ensure dates are valid
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })


# ============ SUBJECT MODEL ============

class Subject(models.Model):
    """Academic subject model"""
    SUBJECT_CATEGORIES = (
        ('core', 'Core Subject'),
        ('elective', 'Elective Subject'),
        ('extracurricular', 'Extracurricular'),
        ('technical', 'Technical/Vocational'),
        ('arts', 'Arts & Music'),
        ('sports', 'Sports & Physical Education'),
    )
    
    DIFFICULTY_LEVELS = (
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('honors', 'Honors'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, help_text="Subject code, e.g., MATH, ENG, BIO")
    category = models.CharField(max_length=20, choices=SUBJECT_CATEGORIES, default='core')
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='basic')
    
    # Subject details
    description = models.TextField(blank=True)
    objectives = models.JSONField(default=list, help_text="Learning objectives")
    prerequisites = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        blank=True, 
        help_text="Required subjects"
    )
    
    # Grading
    max_score = models.IntegerField(default=100, help_text="Maximum score for this subject")
    pass_score = models.IntegerField(default=40, help_text="Minimum passing score")
    
    # Configuration
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_subject'
        unique_together = ['school', 'code']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['category', 'difficulty_level']),
            models.Index(fields=['code']),
            models.Index(fields=['display_order']),
        ]
        ordering = ['display_order', 'name']
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'
    
    def __str__(self):
        return f"{self.name} ({self.code}) - {self.school.name}"
    
    @property
    def full_name(self) -> str:
        return f"{self.name} ({self.code})"
    
    def get_teachers(self):
        """Get all teachers who can teach this subject."""
        try:
            Staff = _get_model('Staff', 'users')
            return Staff.objects.filter(
                school=self.school,
                is_active=True,
                is_teaching_staff=True,
                subjects__id=self.id  # Assuming Staff has subjects ManyToManyField
            ).distinct()
        except LookupError:
            return None
    
    def get_classes_offering(self):
        """Get all classes that offer this subject."""
        return Class.objects.filter(
            classsubject__subject=self,
            is_active=True
        ).distinct()
    
    def clean(self):
        """Validate subject data."""
        if self.max_score <= 0:
            raise ValidationError({
                'max_score': 'Maximum score must be greater than 0.'
            })
        
        if self.pass_score < 0 or self.pass_score > self.max_score:
            raise ValidationError({
                'pass_score': f'Pass score must be between 0 and {self.max_score}.'
            })


# ============ CLASS SUBJECT MODEL ============

class ClassSubject(models.Model):
    """Subjects offered by each class"""
    class_instance = models.ForeignKey(
        Class, 
        on_delete=models.CASCADE,
        related_name='subjects_offered'
    )
    subject = models.ForeignKey(
        Subject, 
        on_delete=models.CASCADE,
        related_name='class_offerings'
    )
    teacher = models.ForeignKey(
        'users.Staff', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='teaching_assignments'
    )
    is_compulsory = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Additional configuration
    periods_per_week = models.IntegerField(default=5, help_text="Number of periods per week")
    elective_group = models.CharField(max_length=50, blank=True, help_text="Elective group name")
    
    class Meta:
        db_table = 'core_class_subject'
        unique_together = ['class_instance', 'subject']
        ordering = ['display_order', 'subject__name']
        indexes = [
            models.Index(fields=['class_instance', 'is_compulsory']),
            models.Index(fields=['teacher']),
            models.Index(fields=['elective_group']),
        ]
        verbose_name = 'Class Subject'
        verbose_name_plural = 'Class Subjects'
    
    def __str__(self):
        return f"{self.class_instance.name} - {self.subject.name}"
    
    def clean(self):
        """Validate class subject assignment."""
        # Ensure subject belongs to same school
        if self.subject.school != self.class_instance.school:
            raise ValidationError({
                'subject': 'Subject must be from the same school.'
            })
        
        # Ensure teacher belongs to same school
        if self.teacher and self.teacher.school != self.class_instance.school:
            raise ValidationError({
                'teacher': 'Teacher must be from the same school.'
            })
        
        # Validate periods_per_week
        if self.periods_per_week <= 0 or self.periods_per_week > 20:
            raise ValidationError({
                'periods_per_week': 'Periods per week must be between 1 and 20.'
            })


# ============ CLASS CREATION TEMPLATE MODEL ============

class ClassCreationTemplate(models.Model):
    """Template for automatically creating classes during school setup"""
    SCHOOL_TYPES = (
        ('nursery', 'Nursery Only'),
        ('primary', 'Primary Only'), 
        ('secondary', 'Secondary Only'),
        ('combined', 'Nursery & Primary'),
        ('full', 'Full K-12'),
    )
    
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPES)
    template_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    configuration = models.JSONField(help_text="Template configuration for classes")
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_class_template'
        indexes = [
            models.Index(fields=['school_type', 'is_active']),
        ]
        verbose_name = 'Class Template'
        verbose_name_plural = 'Class Templates'
        ordering = ['template_name']
    
    def __str__(self):
        return f"{self.template_name} ({self.school_type})"
    
    def create_classes_for_school(self, school: School) -> List[Class]:
        """Create classes for a school using this template."""
        created_classes = []
        
        try:
            # Parse configuration
            class_configs = self.configuration.get('classes', [])
            academic_year = school.academic_years.filter(is_current=True).first()
            
            for config in class_configs:
                # Create class category if specified
                category = None
                if config.get('category'):
                    category, _ = ClassCategory.objects.get_or_create(
                        school=school,
                        name=config['category'],
                        defaults={
                            'section': config.get('section', 'primary'),
                            'display_order': config.get('order', 0)
                        }
                    )
                
                # Create the class
                class_instance = Class.objects.create(
                    school=school,
                    name=config['name'],
                    class_type='academic',
                    category=category,
                    academic_year=academic_year,
                    max_students=config.get('max_students', 40),
                    room_number=config.get('room_number', ''),
                    is_active=True
                )
                
                created_classes.append(class_instance)
            
            logger.info(f"Created {len(created_classes)} classes for school {school.name} using template {self.template_name}")
            
        except Exception as e:
            logger.error(f"Error creating classes from template {self.template_name}: {e}")
        
        return created_classes