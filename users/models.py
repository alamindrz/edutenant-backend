# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal
import logging

# SHARED IMPORTS - NEW ARCHITECTURE
from shared.constants import (
    StatusChoices,
    PARENT_PHONE_FIELD,
    CLASS_MODEL_PATH
)

logger = logging.getLogger(__name__)


class User(AbstractUser):
    """Custom user model for multi-tenant support."""

    username = models.CharField(
        _("username"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("Optional. 150 characters or fewer."),
    )

    email = models.EmailField(_("email address"), unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # ✅ Consistent with shared

    # Use string reference to avoid circular import
    current_school = models.ForeignKey(
        "core.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_users'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Keep username for now to avoid issues

    class Meta:
        db_table = 'auth_user'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone_number']),
        ]

    def __str__(self):
        return self.email


class SchoolOnboardingTemplate(models.Model):
    """
    Template for automatically configuring new schools based on type.
    """
    name = models.CharField(max_length=100, help_text="Template name")
    school_type = models.CharField(max_length=20, choices=[], blank=True)  # Will be set from core
    configuration = models.JSONField(help_text="Template configuration JSON")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'schools_template'

    def __str__(self):
        return f"{self.name} ({self.school_type})"


class Scholarship(models.Model):
    """Scholarship definition for students."""
    SCHOLARSHIP_TYPES = (
        ('merit', 'Merit-Based'),
        ('need', 'Need-Based'),
        ('sports', 'Sports'),
        ('arts', 'Arts'),
        ('staff', 'Staff Discount'),
        ('external', 'External Sponsorship'),
    )

    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    scholarship_type = models.CharField(max_length=20, choices=SCHOLARSHIP_TYPES)
    description = models.TextField(blank=True)

    # Financial details
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount on fees"
    )
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fixed amount discount (alternative to percentage)"
    )
    max_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum discount amount"
    )

    # Eligibility criteria
    eligibility_criteria = models.JSONField(default=list, blank=True)
    required_documents = models.JSONField(default=list, blank=True)

    # Availability
    total_slots = models.PositiveIntegerField(null=True, blank=True)
    slots_taken = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Application period
    application_start = models.DateField(null=True, blank=True)
    application_end = models.DateField(null=True, blank=True)

    # Metadata
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'schools_scholarship'
        verbose_name = 'Scholarship'
        verbose_name_plural = 'Scholarships'
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['scholarship_type']),
        ]

    def __str__(self):
        return f"{self.name} - {self.school.name}"

    @property
    def is_open(self):
        """Check if scholarship applications are open."""
        if not self.is_active:
            return False

        today = timezone.now().date()

        if self.application_start and today < self.application_start:
            return False
        if self.application_end and today > self.application_end:
            return False

        if self.total_slots and self.slots_taken >= self.total_slots:
            return False

        return True

    @property
    def available_slots(self):
        """Get number of available slots."""
        if not self.total_slots:
            return None
        return max(0, self.total_slots - self.slots_taken)

    def calculate_discount(self, base_amount):
        """Calculate discount amount."""
        if self.fixed_amount > 0:
            discount = self.fixed_amount
        else:
            discount = base_amount * (self.discount_percentage / Decimal('100'))

        if self.max_amount:
            discount = min(discount, self.max_amount)

        return discount.quantize(Decimal('0.01'))


class Role(models.Model):
    """Enhanced role-based access control with real permissions."""
    ROLE_CATEGORIES = (
        ('administration', 'Administration'),
        ('academic', 'Academic'),
        ('student', 'Student'),
        ('parent', 'Parent'),
        ('support', 'Support Staff'),
    )

    # Core role information
    name = models.CharField(max_length=100, help_text="Role display name")
    category = models.CharField(max_length=50, choices=ROLE_CATEGORIES)
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)

    # Permissions system - using shared StatusChoices
    permissions = models.JSONField(default=list, help_text="List of permission strings")
    is_system_role = models.BooleanField(default=False)
    system_role_type = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, help_text="Role description and responsibilities")

    # Role management - align with shared decorators
    can_manage_roles = models.BooleanField(default=False, help_text="Can create/edit roles")
    can_manage_staff = models.BooleanField(default=False, help_text="Can manage staff members")
    can_manage_students = models.BooleanField(default=False, help_text="Can manage students")
    can_manage_academics = models.BooleanField(default=False, help_text="Can manage academic records")
    can_manage_finances = models.BooleanField(default=False, help_text="Can manage financial records")
    can_view_reports = models.BooleanField(default=False, help_text="Can view reports")
    can_communicate = models.BooleanField(default=False, help_text="Can send communications")

    # Operational
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_role'
        unique_together = ['school', 'name']
        indexes = [
            models.Index(fields=['school', 'is_system_role']),
            models.Index(fields=['school', 'category']),
        ]

    def __str__(self):
        return f"{self.name} - {self.school.name}"

    def has_permission(self, permission):
        """Check if role has specific permission."""
        return permission in self.permissions or '*' in self.permissions

    def get_permissions_display(self):
        """Get human-readable permissions list."""
        # Use shared constants where possible
        from shared.constants import StatusChoices
        permission_map = {
            'manage_roles': 'Manage Roles',
            'manage_staff': 'Manage Staff',
            'manage_students': 'Manage Students',
            'manage_academics': 'Manage Academics',
            'manage_finances': 'Manage Finances',
            'view_reports': 'View Reports',
            'communicate': 'Send Communications',
            'manage_attendance': 'Manage Attendance',
            'manage_scores': 'Manage Scores',
            'pay_fees': 'Pay Fees',
            'view_children': 'View Children Info',
            # Shared status permissions
            StatusChoices.APPROVED: 'Approve Items',
            StatusChoices.REJECTED: 'Reject Items',
            StatusChoices.PENDING: 'Review Pending Items',
        }
        return [permission_map.get(p, p) for p in self.permissions]


class Staff(models.Model):
    """Staff member model for school employees."""
    EMPLOYMENT_TYPES = (
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('volunteer', 'Volunteer'),
        ('temporary', 'Temporary'),
    )

    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )

    MARITAL_STATUS_CHOICES = (
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    )

    # Basic information
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    staff_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Staff identification number",
        blank=True  # Allow blank initially, will be auto-generated
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(null=True, blank=True)

    # Personal information
    marital_status = models.CharField(
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        blank=True,
        help_text="Marital status"
    )
    nationality = models.CharField(max_length=100, default='Nigerian', blank=True)
    state_of_origin = models.CharField(max_length=100, blank=True)
    lga_of_origin = models.CharField(max_length=100, blank=True, help_text="Local Government Area")

    # Employment details
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='full_time')
    date_joined = models.DateField(default=timezone.now)
    position = models.CharField(max_length=100, help_text="Job title/position")
    department = models.CharField(max_length=100, blank=True, help_text="Department/Section")

    # Professional information
    qualification = models.CharField(
        max_length=100,
        blank=True,
        help_text="Highest qualification (e.g., B.Sc, M.Ed, PhD)"
    )
    specialization = models.CharField(
        max_length=200,
        blank=True,
        help_text="Area of specialization"
    )
    years_of_experience = models.PositiveIntegerField(
        default=0,
        help_text="Years of teaching/professional experience"
    )

    # Contact information - using shared field names
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True)  # ✅ Consistent with shared
    alternate_phone = models.CharField(max_length=20, blank=True, help_text="Alternate phone number")
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True)

    # Bank & official information
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=200, blank=True)
    tax_identification_number = models.CharField(max_length=20, blank=True)
    insurance_number = models.CharField(max_length=50, blank=True, help_text="NHIS or other insurance")

    # Academic qualifications (detailed)
    qualifications = models.JSONField(
        default=list,
        blank=True,
        help_text="List of qualifications with details"
    )

    # Teaching assignments (if applicable)
    subjects = models.ManyToManyField(
        'core.Subject',
        blank=True,
        related_name='teaching_staff',
        help_text="Subjects this staff member teaches"
    )
    # ✅ FIXED: Using core.Class with consistent field name
    assigned_classes = models.ManyToManyField(  # Changed from class_groups to assigned_classes
        'core.Class',
        blank=True,
        related_name='assigned_staff',
        help_text="Academic classes this staff member is assigned to"
    )

    # Status and tracking
    is_active = models.BooleanField(default=True)
    is_teaching_staff = models.BooleanField(default=True, help_text="Whether this staff teaches classes")
    is_management = models.BooleanField(default=False, help_text="Part of school management team")

    # Dates and tracking
    next_of_kin = models.TextField(blank=True, help_text="Next of kin details")
    medical_information = models.TextField(blank=True, help_text="Medical conditions or allergies")
    notes = models.TextField(blank=True, help_text="Additional notes")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_review_date = models.DateField(null=True, blank=True, help_text="Last performance review")
    next_review_date = models.DateField(null=True, blank=True, help_text="Next performance review")

    class Meta:
        db_table = 'users_staff'
        verbose_name = 'Staff Member'
        verbose_name_plural = 'Staff Members'
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'department']),
            models.Index(fields=['school', 'position']),
            models.Index(fields=['staff_id']),
            models.Index(fields=['email']),
            models.Index(fields=['date_joined']),
            models.Index(fields=['is_teaching_staff']),
        ]
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.full_name} - {self.position} ({self.staff_id})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self):
        """Formal display name with title."""
        title = "Mr." if self.gender == 'M' else "Mrs." if self.gender == 'F' and self.marital_status == 'married' else "Ms."
        return f"{title} {self.last_name}"

    @property
    def age(self):
        """Calculate age from date of birth."""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def years_of_service(self):
        """Calculate years of service at the school."""
        today = timezone.now().date()
        return today.year - self.date_joined.year - (
            (today.month, today.day) < (self.date_joined.month, self.date_joined.day)
        )

    def generate_staff_id(self):
        """Generate unique staff ID if not provided."""
        if not self.staff_id:
            school_code = self.school.subdomain.upper()[:3] if self.school.subdomain else 'SCH'
            year = self.date_joined.year
            sequence = Staff.objects.filter(
                school=self.school,
                date_joined__year=year
            ).count() + 1

            self.staff_id = f"{school_code}/STAFF/{year}/{sequence:04d}"

    def clean(self):
        """Validate staff data before saving."""
        from django.core.exceptions import ValidationError

        # Validate email uniqueness
        if self.email and Staff.objects.filter(
            email=self.email
        ).exclude(pk=self.pk).exists():
            raise ValidationError({'email': 'A staff member with this email already exists.'})

        # Validate date of birth
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({'date_of_birth': 'Date of birth cannot be in the future.'})

        # Validate date joined
        if self.date_joined and self.date_joined > timezone.now().date():
            raise ValidationError({'date_joined': 'Date joined cannot be in the future.'})

        # Auto-set flags based on position
        if self.position:
            teaching_positions = ['teacher', 'lecturer', 'instructor', 'tutor']
            self.is_teaching_staff = any(pos in self.position.lower() for pos in teaching_positions)

            management_positions = ['principal', 'head', 'director', 'manager', 'admin', 'coordinator']
            self.is_management = any(pos in self.position.lower() for pos in management_positions)

    def save(self, *args, **kwargs):
        """Auto-generate staff ID."""
        self.full_clean()  # Run validation

        if not self.staff_id:
            self.generate_staff_id()

        super().save(*args, **kwargs)

    def create_user_account(self, password=None):
        """
        Create a user account for this staff member.
        This should be moved to a service, but kept for backward compatibility.
        """
        if self.user:
            return self.user

        try:
            # Use get_user_model() for flexibility
            User = settings.AUTH_USER_MODEL

            # Check if user already exists with this email
            try:
                user = User.objects.get(email=self.email)
            except User.DoesNotExist:
                # Create new user
                if password is None:
                    password = User.objects.make_random_password()

                user = User.objects.create_user(
                    email=self.email,
                    username=self.email,
                    password=password,
                    first_name=self.first_name,
                    last_name=self.last_name,
                    phone_number=self.phone_number
                )

            # Create profile with appropriate role
            try:
                # Get or create default teacher role
                role, created = Role.objects.get_or_create(
                    school=self.school,
                    system_role_type='teacher',
                    defaults={
                        'name': 'Teacher',
                        'category': 'academic',
                        'permissions': [
                            'manage_attendance',
                            'manage_scores',
                            'view_reports',
                            'communicate'
                        ]
                    }
                )
            except Role.DoesNotExist:
                # Fallback to any academic role
                role = Role.objects.filter(
                    school=self.school,
                    category='academic'
                ).first()

            if role:
                # Create or update profile
                Profile.objects.update_or_create(
                    user=user,
                    school=self.school,
                    defaults={'role': role, 'phone_number': self.phone_number}
                )


            self.user = user
            self.save(update_fields=['user'])

            return user
        except Exception as e:
            logger.error(f"Error creating user account for staff {self.email}: {e}")
            return None

    @property
    def current_classes(self):
        """Get current class assignments."""
        return self.assigned_classes.all()  # ✅ Updated field name

    @property
    def current_subjects(self):
        """Get current subject assignments."""
        return self.subjects.all()

    def get_attendance_records(self, start_date=None, end_date=None):
        """Get attendance records for this staff member."""
        # Use string reference to avoid import issues
        from attendance.models import TeacherAttendance

        records = TeacherAttendance.objects.filter(staff=self)

        if start_date:
            records = records.filter(date__gte=start_date)
        if end_date:
            records = records.filter(date__lte=end_date)

        return records.order_by('-date')


class StaffAssignment(models.Model):
    """Assignment of staff to roles and responsibilities."""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'users_staff_assignment'
        unique_together = ['staff', 'role']
        indexes = [
            models.Index(fields=['staff', 'is_active']),
        ]

    def __str__(self):
        return f"{self.staff} - {self.role}"


class Profile(models.Model):
    """User profile for school-specific information."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    phone_number = models.CharField(max_length=32, blank=True, null=True)  # ✅ Consistent

    class Meta:
        db_table = 'users_profile'
        unique_together = ['user', 'school']
        indexes = [
            models.Index(fields=['user', 'school']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.school.name}"


class StaffInvitation(models.Model):
    """Model for inviting teachers/staff to join the school."""
    INVITATION_STATUS = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
    )

    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    email = models.EmailField()
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=INVITATION_STATUS, default='pending')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField(blank=True)

    class Meta:
        db_table = 'users_staff_invitation'
        unique_together = ['school', 'email']
        indexes = [
            models.Index(fields=['token', 'status']),
            models.Index(fields=['school', 'status']),
        ]

    def __str__(self):
        return f"{self.email} - {self.school.name}"

    def is_valid(self):
        return self.status == 'pending' and self.expires_at > timezone.now()


class OpenPosition(models.Model):
    """Model for school's open teaching positions."""
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    requirements = models.TextField(blank=True, help_text="Required qualifications and experience")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_open_position'
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]

    def __str__(self):
        return f"{self.title} - {self.school.name}"

    @property
    def application_count(self):
        """Count pending applications for this position."""
        return self.teacherapplication_set.filter(status='pending').count()


class TeacherApplication(models.Model):
    """Model for teachers applying to join schools."""
    APPLICATION_STATUS = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    )

    APPLICATION_TYPE = (
        ('new_teacher', 'New Teacher (No Experience)'),
        ('experienced', 'Experienced Teacher'),
        ('transfer', 'Transfer from Another School'),
    )

    # Basic information
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    position = models.ForeignKey(OpenPosition, on_delete=models.CASCADE, null=True, blank=True)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)  # ✅ Consistent field name

    # Application details
    application_type = models.CharField(max_length=20, choices=APPLICATION_TYPE, default='experienced')
    position_applied = models.CharField(max_length=100, help_text="Position being applied for")
    years_of_experience = models.PositiveIntegerField(default=0)
    qualification = models.CharField(max_length=100, help_text="Highest qualification")
    specialization = models.CharField(max_length=200, blank=True, help_text="Area of specialization")

    # Application content
    cover_letter = models.TextField(blank=True, help_text="Why you want to join this school")
    resume = models.FileField(upload_to='teacher_resumes/', null=True, blank=True)
    certificates = models.FileField(upload_to='teacher_certificates/', null=True, blank=True)

    # Status and tracking - using shared StatusChoices where possible
    status = models.CharField(max_length=20, choices=APPLICATION_STATUS, default='pending')
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_applications'
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_teacher_application'
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.school.name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def is_pending(self):
        return self.status == 'pending'

    def approve(self, approved_by):
        """Approve this application and create staff record."""
        # ✅ This should be moved to a shared service
        # For now, we'll keep it but log that it should be refactored
        logger.warning("TeacherApplication.approve() should be moved to shared service")

        from .services import StaffService
        return StaffService.approve_application(self, approved_by)

    def reject(self, rejected_by, reason=""):
        """Reject this application."""
        self.status = 'rejected'
        self.status_changed_by = rejected_by
        self.status_changed_at = timezone.now()
        self.save()
