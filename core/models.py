# core/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from users.models import User, Staff, School

class ClassCategory(models.Model):
    """Category for grouping classes (e.g., Primary, Secondary, JSS, SSS)"""
    SCHOOL_SECTIONS = (
        ('nursery', 'Nursery'),
        ('primary', 'Primary'),
        ('jss', 'Junior Secondary'),
        ('sss', 'Senior Secondary'),
        ('special', 'Special Needs'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    section = models.CharField(max_length=20, choices=SCHOOL_SECTIONS)
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'core_class_category'
        unique_together = ['school', 'name']
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"




class Class(models.Model):
    """Main Class model (e.g., SSS 1A, Primary 3B)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ClassCategory, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="e.g., SSS 1A, Primary 3B")
    code = models.CharField(max_length=20, unique=True, help_text="Unique class code")
    
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
    current_strength = models.IntegerField(default=0)
    room_number = models.CharField(max_length=20, blank=True)
    
    # Academic information
    academic_session = models.CharField(max_length=50, blank=True, help_text="e.g., 2024/2025")
    is_graduated = models.BooleanField(default=False)
    graduation_date = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_class'
        unique_together = ['school', 'name']
        ordering = ['category__display_order', 'name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['form_master', 'is_active']),
        ]
        verbose_name_plural = "Classes"
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    def save(self, *args, **kwargs):
        # Auto-generate code if not provided
        if not self.code:
            self.code = f"CLS{self.school.id}{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        # Update current strength before saving
        self.update_strength()
        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        return f"{self.category.name} - {self.name}"
    
    def update_strength(self):
        """Update current student count from related students"""
        # Use the reverse relationship 'students' that we created
        self.current_strength = self.students.filter(is_active=True, admission_status='enrolled').count()
        # Don't call save() here to avoid recursion
    
    def can_add_student(self):
        """Check if class can accept more students"""
        return self.current_strength < self.max_students
    
    def get_students(self):
        """Get all active students in this class"""
        return self.students.filter(is_active=True, admission_status='enrolled')
    
    def get_student_list(self):
        """Get student list for display"""
        return self.students.filter(
            is_active=True, 
            admission_status='enrolled'
        ).select_related('parent').order_by('first_name', 'last_name')
    
    @property
    def capacity_percentage(self):
        """Get class capacity percentage"""
        if self.max_students == 0:
            return 0
        return (self.current_strength / self.max_students) * 100
    
    @property
    def is_full(self):
        """Check if class is at full capacity"""
        return self.current_strength >= self.max_students


class ClassMonitor(models.Model):
    """Student monitors for each class"""
    MONITOR_ROLES = (
        ('head', 'Head Monitor'),
        ('assistant', 'Assistant Monitor'),
        ('prefect', 'Prefect'),
        ('captain', 'Captain'),
    )
    
    class_instance = models.ForeignKey(Class, on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE)  # We'll create this
    role = models.CharField(max_length=20, choices=MONITOR_ROLES)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Responsibilities
    responsibilities = models.JSONField(default=list, help_text="List of monitor responsibilities")
    
    # Audit
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'core_class_monitor'
        unique_together = ['class_instance', 'student', 'role']
        ordering = ['class_instance', 'role', 'start_date']
    
    def __str__(self):
        return f"{self.student.full_name} - {self.get_role_display()} of {self.class_instance.name}"


class Subject(models.Model):
    """Academic subject model"""
    SUBJECT_CATEGORIES = (
        ('core', 'Core Subject'),
        ('elective', 'Elective Subject'),
        ('extracurricular', 'Extracurricular'),
        ('technical', 'Technical/Vocational'),
    )
    
    DIFFICULTY_LEVELS = (
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, help_text="Subject code, e.g., MATH, ENG, BIO")
    category = models.CharField(max_length=20, choices=SUBJECT_CATEGORIES, default='core')
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='basic')
    
    # Subject details
    description = models.TextField(blank=True)
    objectives = models.JSONField(default=list, help_text="Learning objectives")
    prerequisites = models.ManyToManyField('self', symmetrical=False, blank=True, help_text="Required subjects")
    
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
        ]
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.code}) - {self.school.name}"
    
    @property
    def full_name(self):
        return f"{self.name} ({self.code})"
    
    def get_teachers(self):
        """Get all teachers who can teach this subject."""
        from attendance.models import Staff
        return Staff.objects.filter(
            school=self.school,
            is_active=True,
            position__in=['teacher', 'head teacher']
        )
    
    def get_classes_offering(self):
        """Get all classes that offer this subject."""
        return Class.objects.filter(
            classsubject__subject=self,
            is_active=True
        ).distinct()




class ClassSubject(models.Model):
    """Subjects offered by each class"""
    class_instance = models.ForeignKey(Class, on_delete=models.CASCADE)
    subject = models.ForeignKey('core.Subject', on_delete=models.CASCADE)  # ✅ FIXED: reference to core.Subject
    teacher = models.ForeignKey('users.Staff', on_delete=models.SET_NULL, null=True, blank=True)
    is_compulsory = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'core_class_subject'
        unique_together = ['class_instance', 'subject']
        ordering = ['display_order', 'subject__name']  # ✅ FIXED: now subject exists
    
    def __str__(self):
        return f"{self.class_instance.name} - {self.subject.name}"


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
    configuration = models.JSONField(help_text="Template configuration for classes")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'core_class_template'
    
    def __str__(self):
        return f"{self.template_name} ({self.school_type})"
        


