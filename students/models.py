# students/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from users.models import School
from django.utils import timezone


User = get_user_model()

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
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    level = models.CharField(max_length=20, choices=SCHOOL_LEVELS)
    name = models.CharField(max_length=100, help_text="Level name (e.g., 'Primary 1', 'JSS 2')")
    order = models.IntegerField(default=0, help_text="Display order within level")
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'students_education_level'
        unique_together = ['school', 'level', 'name']
        ordering = ['school', 'level', 'order']
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"

class ClassGroup(models.Model):
    """
    Represents a class group within an education level.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="Class name (e.g., 'Primary 1A')")
    education_level = models.ForeignKey(EducationLevel, on_delete=models.CASCADE)
    class_teacher = models.ForeignKey('users.Profile', on_delete=models.SET_NULL, null=True, blank=True, related_name='class_teacher_of')
    teachers = models.ManyToManyField('users.Profile', blank=True, related_name='teaching_classes')
    capacity = models.IntegerField(default=40, help_text="Maximum student capacity")
    
    class Meta:
        db_table = 'students_class_group'
        unique_together = ['school', 'name']
        indexes = [
            models.Index(fields=['school', 'education_level']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    @property
    def student_count(self):
        """Get number of active students in class."""
        return self.student_set.filter(is_active=True).count()
    
    @property
    def is_full(self):
        """Check if class has reached capacity."""
        return self.student_count >= self.capacity




class Parent(models.Model):
    """
    Represents a parent who can have multiple children in the school.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    address = models.TextField()
    relationship = models.CharField(max_length=50, default='Parent')
    
    # Add these fields for staff child tracking
    is_staff_child = models.BooleanField(default=False, help_text="Is this a staff member's child?")
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
            models.Index(fields=['is_staff_child']),  # Add index for filtering
        ]
    
    def __str__(self):
        if self.is_staff_child and self.staff_member:
            return f"{self.full_name} (Staff: {self.staff_member.user.get_full_name()}) - {self.school.name}"
        return f"{self.first_name} {self.last_name} - {self.school.name}"
    
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
    
    def create_user_account(self):
        """Create user account for parent."""
        if self.user:
            return self.user
        
        user = User.objects.create_user(
            email=self.email,
            username=self.email,
            password=User.objects.make_random_password(),
            first_name=self.first_name,
            last_name=self.last_name,
            phone_number=self.phone_number
        )
        
        # Create parent profile
        from users.models import Profile, Role
        parent_role = Role.objects.get(school=self.school, system_role_type='parent')
        Profile.objects.create(
            user=user,
            school=self.school,
            role=parent_role,
            parent_profile=self,
            phone_number=self.phone_number
        )
        
        self.user = user
        self.save()
        return user


class Student(models.Model):
    """
    Represents a student enrolled in the school.
    """
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    
    ADMISSION_STATUS_CHOICES = (
        ('applied', 'Applied'),
        ('under_review', 'Under Review'), 
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('enrolled', 'Enrolled'),
    )
    
    # Basic Information
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    admission_number = models.CharField(max_length=50, unique=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField()
    admission_status = models.CharField(
        max_length=20,
        choices=ADMISSION_STATUS_CHOICES,
        default='applied'
    )
    
    # Add this field
    is_staff_child = models.BooleanField(default=False, help_text="Is this a staff member's child?")


    # Application-specific fields (for pre-enrollment)
    previous_school = models.CharField(max_length=255, blank=True)
    previous_class = models.CharField(max_length=100, blank=True)
    application_notes = models.TextField(blank=True)
    
    # Parent relationship
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    
    # Academic information
    education_level = models.ForeignKey(EducationLevel, on_delete=models.PROTECT)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.SET_NULL, null=True, blank=True)
    
    # ✅ ADDED: Current class assignment
    current_class = models.ForeignKey(
        'core.Class',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="Student's current class assignment"
    )
    
    # Admission dates
    application_date = models.DateTimeField(null=True, blank=True)
    admission_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    # Medical information
    medical_conditions = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=20, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students_student'
        indexes = [
            models.Index(fields=['school', 'admission_number']),
            models.Index(fields=['school', 'parent']),
            models.Index(fields=['school', 'education_level']),
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'current_class']),  # ✅ Added index
        ]
        ordering = ['admission_number']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        """Calculate student's current age."""
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    def generate_admission_number(self):
        """Generate unique admission number if not provided."""
        if not self.admission_number:
            school_code = self.school.subdomain.upper()[:3]
            year = self.admission_date.year
            sequence = Student.objects.filter(
                school=self.school,
                admission_date__year=year
            ).count() + 1
            
            self.admission_number = f"{school_code}/{year}/{sequence:04d}"
    
    def save(self, *args, **kwargs):
        if not self.admission_number:
            self.generate_admission_number()
        
        # Update class strength when student is saved
        old_class = None
        if self.pk:
            try:
                old_student = Student.objects.get(pk=self.pk)
                old_class = old_student.current_class
            except Student.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update old class strength if class changed
        if old_class and old_class != self.current_class:
            old_class.update_strength()
        
        # Update new class strength
        if self.current_class:
            self.current_class.update_strength()
    
    def delete(self, *args, **kwargs):
        """Update class strength when student is deleted."""
        current_class = self.current_class
        super().delete(*args, **kwargs)
        if current_class:
            current_class.update_strength()
        
        


class AcademicTerm(models.Model):
    """
    Represents academic terms within a session with enhanced tracking.
    """
    TERM_CHOICES = (
        ('first', 'First Term'),
        ('second', 'Second Term'), 
        ('third', 'Third Term'),
    )
    
    TERM_STATUS = (
        ('upcoming', 'Upcoming'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),  # For strikes, emergencies
        ('closed', 'Closed'),  # Ended normally
        ('extended', 'Extended'),  # Term extended beyond planned end
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    academic_year = models.CharField(max_length=20, help_text="e.g., 2024/2025")
    
    # Core dates
    start_date = models.DateField()
    end_date = models.DateField()
    actual_end_date = models.DateField(null=True, blank=True, help_text="Actual end date if extended")
    
    # Duration in weeks (flexible)
    planned_weeks = models.PositiveIntegerField(default=12, help_text="Planned duration in weeks")
    actual_weeks = models.PositiveIntegerField(null=True, blank=True, help_text="Actual duration in weeks")
    
    # Status management
    status = models.CharField(max_length=15, choices=TERM_STATUS, default='upcoming')
    is_active = models.BooleanField(default=False)
    
    # Break periods
    mid_term_break_start = models.DateField(null=True, blank=True)
    mid_term_break_end = models.DateField(null=True, blank=True)
    
    # Emergency closures
    closure_start = models.DateField(null=True, blank=True, help_text="Unexpected closure start (strike, pandemic)")
    closure_end = models.DateField(null=True, blank=True, help_text="Unexpected closure end")
    closure_reason = models.TextField(blank=True, help_text="Reason for closure")
    
    # Metadata - REMOVE auto_now_add and use default instead
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'students_academic_term'
        unique_together = ['school', 'academic_year', 'term']
        ordering = ['-academic_year', 'start_date']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
    
    def __str__(self):
        status_display = "✓" if self.is_active else "✗"
        return f"{self.name} - {self.academic_year} [{status_display}]"
        
    
    def clean(self):
        """Validate term dates and logic."""
        from django.core.exceptions import ValidationError
        
        if self.start_date >= self.end_date:
            raise ValidationError("End date must be after start date.")
        
        if self.actual_end_date and self.actual_end_date < self.start_date:
            raise ValidationError("Actual end date cannot be before start date.")
        
        # Validate mid-term break
        if self.mid_term_break_start and self.mid_term_break_end:
            if self.mid_term_break_start >= self.mid_term_break_end:
                raise ValidationError("Mid-term break end must be after start.")
            if (self.mid_term_break_start < self.start_date or 
                self.mid_term_break_end > self.end_date):
                raise ValidationError("Mid-term break must be within term dates.")
        
        # Validate closure period
        if self.closure_start and self.closure_end:
            if self.closure_start >= self.closure_end:
                raise ValidationError("Closure end must be after start.")
    
    def save(self, *args, **kwargs):
        """Auto-calculate weeks and handle status logic."""
        # Calculate planned weeks
        if self.start_date and self.end_date:
            days_diff = (self.end_date - self.start_date).days
            self.planned_weeks = max(12, days_diff // 7)  # Minimum 12 weeks
        
        # Calculate actual weeks if term ended
        if self.actual_end_date:
            days_diff = (self.actual_end_date - self.start_date).days
            self.actual_weeks = days_diff // 7
        
        # Auto-set is_active based on status
        self.is_active = (self.status == 'active')
        
        super().save(*args, **kwargs)
    
    @property
    def is_currently_active(self):
        """Check if term is currently active based on dates and status."""
        today = timezone.now().date()
        
        if self.status != 'active':
            return False
        
        return self.start_date <= today <= (self.actual_end_date or self.end_date)
    
    @property
    def total_working_days(self):
        """Calculate total working days excluding weekends and breaks."""
        from datetime import timedelta
        
        total_days = (self.end_date - self.start_date).days + 1
        working_days = 0
        
        current_date = self.start_date
        for _ in range(total_days):
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5:
                # Check if not in mid-term break
                if not self._is_date_in_break(current_date):
                    working_days += 1
            current_date += timedelta(days=1)
        
        return working_days
    
    def _is_date_in_break(self, date):
        """Check if date falls within mid-term break."""
        if self.mid_term_break_start and self.mid_term_break_end:
            return self.mid_term_break_start <= date <= self.mid_term_break_end
        return False
    
    def is_school_day(self, date):
        """
        Check if a specific date is a valid school day.
        Consider weekends, breaks, and closures.
        """
        # Check if date is within term
        if not (self.start_date <= date <= (self.actual_end_date or self.end_date)):
            return False
        
        # Check if weekend
        if date.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check if in mid-term break
        if self._is_date_in_break(date):
            return False
        
        # Check if in closure period
        if self.closure_start and self.closure_end:
            if self.closure_start <= date <= self.closure_end:
                return False
        
        return True
    
    def get_attendance_dates(self):
        """Get all valid attendance dates for this term."""
        from datetime import timedelta
        
        dates = []
        current_date = self.start_date
        end_date = self.actual_end_date or self.end_date
        
        while current_date <= end_date:
            if self.is_school_day(current_date):
                dates.append(current_date)
            current_date += timedelta(days=1)
        
        return dates
    
    def suspend_term(self, reason="", closure_start=None, closure_end=None):
        """Suspend the term (for strikes, emergencies)."""
        self.status = 'suspended'
        self.closure_start = closure_start or timezone.now().date()
        self.closure_end = closure_end
        self.closure_reason = reason
        self.is_active = False
        self.save()
    
    def resume_term(self, new_end_date=None):
        """Resume a suspended term, optionally extending it."""
        self.status = 'active'
        if new_end_date:
            self.actual_end_date = new_end_date
            self.status = 'extended'
        self.closure_start = None
        self.closure_end = None
        self.closure_reason = ""
        self.is_active = True
        self.save()
    
    def close_term(self):
        """Close the term normally."""
        self.status = 'closed'
        self.actual_end_date = self.actual_end_date or timezone.now().date()
        self.is_active = False
        self.save()
        
        


class Enrollment(models.Model):
    """
    Tracks student enrollment in specific class groups per term.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE)
    academic_term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'students_enrollment'
        unique_together = ['student', 'academic_term']
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['class_group', 'academic_term']),
        ]
    
    def __str__(self):
        return f"{self.student} - {self.class_group} ({self.academic_term})"

class Attendance(models.Model):
    """
    Tracks student attendance.
    """
    ATTENDANCE_STATUS = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused Absence'),
    )
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    academic_term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default='present')
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey('users.Profile', on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'students_attendance'
        unique_together = ['student', 'date']
        indexes = [
            models.Index(fields=['student', 'date']),
            models.Index(fields=['academic_term', 'date']),
        ]
        ordering = ['-date', 'student']
    
    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"


class Score(models.Model):
    """
    Tracks student scores for subjects.
    """
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    subject = models.ForeignKey('core.Subject', on_delete=models.CASCADE)  # ✅ Use core.Subject
    score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Score out of 100")
    maximum_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    assessment_type = models.CharField(max_length=50, help_text="e.g., Test, Exam, Assignment")
    assessment_date = models.DateField()
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey('users.Profile', on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'students_score'
        indexes = [
            models.Index(fields=['enrollment', 'subject']),
            models.Index(fields=['assessment_date']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.student} - {self.subject}: {self.score}"