# admissions/models.py 
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
import uuid
import logging

# SHARED IMPORTS - FIX CIRCULAR DEPENDENCIES
from shared.constants import (
    StatusChoices,
    PaymentMethods,
    CLASS_MODEL_PATH,
    APPLICATION_CLASS_FIELD
)

logger = logging.getLogger(__name__)


class ApplicationForm(models.Model):
    FORM_STATUS = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
    )
    
    school = models.ForeignKey('core.School', on_delete=models.CASCADE, related_name='application_forms')
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=FORM_STATUS, default='draft')
    
    # Enhanced fee configuration
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, default='NGN')
    position_applied = models.CharField(max_length=100, help_text="Position/Class being applied for")
    has_acceptance_fee = models.BooleanField(default=False)
    acceptance_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Enhanced form configuration
    fields = models.JSONField(default=list, help_text="Custom form fields configuration")
    required_documents = models.JSONField(default=list, help_text="List of required documents")
    eligibility_criteria = models.JSONField(default=list, help_text="Eligibility requirements")
    
    # Timeline with validation
    open_date = models.DateTimeField(default=timezone.now)
    close_date = models.DateTimeField()
    
    # Nigerian context
    academic_session = models.CharField(max_length=20, help_text="e.g., 2024/2025")
    # CHANGED: Store Class IDs directly instead of JSON
    available_class_ids = models.JSONField(default=list, help_text="List of Class IDs accepting applications")
    
    # Application limits
    max_applications = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for unlimited")
    applications_so_far = models.PositiveIntegerField(default=0, editable=False)
    
    # Metadata
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'admissions_applicationform'
        verbose_name = 'Application Form'
        verbose_name_plural = 'Application Forms'
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['open_date', 'close_date']),
            models.Index(fields=['slug']),
            models.Index(fields=['academic_session']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    def clean(self):
        """Validate application form data."""
        from django.core.exceptions import ValidationError
        
        # Validate dates
        if self.open_date and self.close_date and self.open_date >= self.close_date:
            raise ValidationError({'close_date': 'Close date must be after open date.'})
        
        # Validate application fee consistency
        if self.is_free and self.application_fee > 0:
            raise ValidationError({
                'is_free': 'Application cannot be marked as free with a fee amount.'
            })
        
        # Validate max_applications
        if self.max_applications is not None and self.max_applications <= 0:
            raise ValidationError({
                'max_applications': 'Maximum applications must be positive or empty.'
            })
        
        # Validate academic_session format
        if self.academic_session and '/' not in self.academic_session:
            raise ValidationError({
                'academic_session': 'Academic session should be in format YYYY/YYYY (e.g., 2024/2025).'
            })
        
        # Validate available_class_ids are integers
        if self.available_class_ids:
            try:
                for class_id in self.available_class_ids:
                    if not isinstance(class_id, int) or class_id <= 0:
                        raise ValidationError({
                            'available_class_ids': f'Invalid Class ID: {class_id}. Must be positive integers.'
                        })
            except (TypeError, ValueError):
                raise ValidationError({
                    'available_class_ids': 'available_class_ids must be a list of integers.'
                })
    
    def save(self, *args, **kwargs):
        """Save application form with auto-generated slug and defaults."""
        self.full_clean()  # Run validation first
        
        # Generate slug if not provided
        if not self.slug:
            school_slug = self.school.subdomain or str(self.school.id)
            base_slug = slugify(f"{school_slug}-{self.name}")
            self.slug = base_slug
            counter = 1
            while ApplicationForm.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        
        # Set default close date if not provided
        if not self.close_date:
            self.close_date = self.open_date + timezone.timedelta(days=90)
        
        super().save(*args, **kwargs)
    
    @property
    def is_open(self):
        """Check if form is currently accepting applications."""
        now = timezone.now()
        return (
            self.status == 'active' and 
            self.open_date <= now <= self.close_date and
            (self.max_applications is None or 
             self.applications_so_far < self.max_applications)
        )
    
    @property
    def days_remaining(self):
        """Get days remaining until form closes."""
        if not self.is_open:
            return 0
        delta = self.close_date - timezone.now()
        return max(0, delta.days)
    
    @property
    def available_classes(self):
        """Get available Class instances for this form."""
        from core.models import Class
        if self.available_class_ids:
            return Class.objects.filter(
                id__in=self.available_class_ids,
                school=self.school
            )
        return Class.objects.filter(school=self.school)


class Application(models.Model):
    APPLICATION_STATUS = (
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('waitlisted', 'Waitlisted'),
    )
    
    PRIORITY_CHOICES = (
        ('urgent', 'Urgent'),
        ('high', 'High'),
        ('normal', 'Normal'),
        ('low', 'Low'),
    )
    
    application_number = models.CharField(max_length=50, unique=True, db_index=True)
    public_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_staff_child = models.BooleanField(default=False, help_text="Is this a staff child application?")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    
    # Core relationships
    form = models.ForeignKey(ApplicationForm, on_delete=models.CASCADE, related_name='applications')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, null=True, blank=True, related_name='applications')
    parent = models.ForeignKey('students.Parent', on_delete=models.CASCADE, related_name='applications')
    
    # Enhanced application data
    data = models.JSONField(default=dict, help_text="Application form data")
    documents = models.JSONField(default=list, help_text="Uploaded documents")
    
    # Status tracking with history
    status = models.CharField(max_length=20, choices=APPLICATION_STATUS, default=StatusChoices.PENDING)
    status_changed_at = models.DateTimeField(auto_now=True)
    status_history = models.JSONField(default=list, help_text="Status change history")
    
    # Payment tracking
    application_fee_paid = models.BooleanField(default=False)
    application_fee_invoice = models.ForeignKey('billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Enhanced review system
    assigned_to = models.ForeignKey('users.Staff', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_applications')
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Class applied for - UPDATED: Use core.Class directly
    applied_class = models.ForeignKey('core.Class', on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    previous_school_info = models.JSONField(default=dict, help_text="Previous school information")
    
    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admissions_application'
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['form', 'status']),
            models.Index(fields=['parent', 'status']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['submitted_at']),
            models.Index(fields=['priority']),
            models.Index(fields=['is_staff_child']),
            models.Index(fields=['applied_class']),
        ]
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"Application {self.application_number}"
    
    def clean(self):
        """Validate application data."""
        from django.core.exceptions import ValidationError
        
        # Validate form belongs to same school as parent
        if self.parent and self.form.school != self.parent.school:
            raise ValidationError({
                'form': 'Application form must belong to the same school as the parent.'
            })
        
        # Validate applied class belongs to same school
        if self.applied_class and self.applied_class.school != self.form.school:
            raise ValidationError({
                'applied_class': 'Applied class must belong to the same school.'
            })
        
        # Validate staff child consistency
        if self.is_staff_child:
            if not self.parent or not self.parent.is_staff_child:
                raise ValidationError({
                    'is_staff_child': 'Parent must be marked as staff child for staff child applications.'
                })
        
        # Validate student belongs to same parent if provided
        if self.student and self.student.parent != self.parent:
            raise ValidationError({
                'student': 'Student must belong to the specified parent.'
            })
        
        # Validate form is open for applications
        if not self.form.is_open:
            raise ValidationError({
                'form': 'This application form is not currently accepting applications.'
            })
        
        # Validate applied class is in form's available classes
        if self.applied_class and self.form.available_class_ids:
            if self.applied_class.id not in self.form.available_class_ids:
                raise ValidationError({
                    'applied_class': f"Class '{self.applied_class.name}' is not available for this application form."
                })
    
    def save(self, *args, **kwargs):
        """Save application with auto-generated number and status tracking."""
        self.full_clean()  # Run validation first
        
        # Generate application number if not provided
        if not self.application_number:
            self.application_number = self.generate_application_number()
        
        # Track status changes
        if self.pk:
            try:
                old_instance = Application.objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    # Add to status history
                    history_entry = {
                        'from_status': old_instance.status,
                        'to_status': self.status,
                        'changed_at': timezone.now().isoformat(),
                        'notes': f"Status changed from {old_instance.status} to {self.status}"
                    }
                    
                    # Add user if available
                    user = getattr(self, '_current_user', None)
                    if user:
                        history_entry['changed_by'] = {
                            'id': user.id,
                            'email': user.email,
                            'name': user.get_full_name()
                        }
                    
                    self.status_history.append(history_entry)
            except Application.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update form application count
        self.form.applications_so_far = self.form.applications.count()
        self.form.save(update_fields=['applications_so_far'])
    
    def generate_application_number(self):
        """Generate unique application number."""
        school_code = self.form.school.subdomain.upper()[:3] if self.form.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        month = timezone.now().strftime('%m')
        unique_id = str(uuid.uuid4().int)[:6].upper()
        return f"APP/{school_code}/{year}{month}/{unique_id}"
    
    @property
    def processing_time(self):
        """Get days since submission."""
        return (timezone.now() - self.submitted_at).days
    
    @property
    def is_overdue(self):
        """Check if application is overdue for review."""
        return self.processing_time > 14 and self.status == 'submitted'
    
    @property
    def student_full_name(self):
        """Get student's full name from data or linked student."""
        if self.student:
            return self.student.full_name
        
        # Fallback to form data
        first_name = self.data.get('first_name', '')
        last_name = self.data.get('last_name', '')
        return f"{first_name} {last_name}".strip()
    
    @property
    def parent_full_name(self):
        """Get parent's full name."""
        if self.parent:
            return self.parent.full_name
        
        # Fallback to form data
        parent_first = self.data.get('parent_first_name', '')
        parent_last = self.data.get('parent_last_name', '')
        return f"{parent_first} {parent_last}".strip()
    
    @property
    def fee_amount(self):
        """Get application fee amount (with staff child discount if applicable)."""
        fee = self.form.application_fee
        
        # Apply staff child discount
        if self.is_staff_child and self.form.school.staff_children_waive_application_fee:
            return 0
        
        return fee


class Admission(models.Model):
    """Enhanced Admission model with better tracking and Nigerian context."""
    ADMISSION_TYPES = (
        ('regular', 'Regular Admission'),
        ('transfer', 'Transfer Student'),
        ('special', 'Special Consideration'),
    )
    
    admission_number = models.CharField(max_length=50, unique=True, db_index=True)
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='admission')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='admissions')
    
    # Enhanced offer details
    admission_type = models.CharField(max_length=20, choices=ADMISSION_TYPES, default='regular')
    
    # UPDATED: Use core.Class for consistency
    offered_class = models.ForeignKey('core.Class', on_delete=models.PROTECT, related_name='admission_offers')
    offer_expires = models.DateTimeField()
    
    # Enhanced acceptance tracking
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    acceptance_notes = models.TextField(blank=True, help_text="Parent's acceptance notes")
    
    # Enhanced fee tracking
    requires_acceptance_fee = models.BooleanField(default=False)
    acceptance_fee_invoice = models.ForeignKey('billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    acceptance_fee_paid = models.BooleanField(default=False)
    acceptance_fee_deadline = models.DateTimeField(null=True, blank=True)
    
    # Nigerian context enhancements
    admission_letter_sent = models.BooleanField(default=False)
    admission_letter_sent_at = models.DateTimeField(null=True, blank=True)
    admission_letter_method = models.CharField(
        max_length=20, 
        default='email', 
        choices=[('email', 'Email'), ('sms', 'SMS'), ('print', 'Printed'), ('whatsapp', 'WhatsApp')]
    )
    
    # Admission conditions and requirements
    conditions = models.JSONField(default=list, help_text="Admission conditions to be met")
    required_documents_submitted = models.BooleanField(default=False)
    documents_verified = models.BooleanField(default=False)
    
    # Timeline tracking
    enrollment_deadline = models.DateTimeField(null=True, blank=True)
    enrollment_completed = models.BooleanField(default=False)
    enrollment_completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey('users.Staff', on_delete=models.SET_NULL, null=True, related_name='created_admissions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admissions_admission'
        verbose_name = 'Admission'
        verbose_name_plural = 'Admissions'
        indexes = [
            models.Index(fields=['admission_number']),
            models.Index(fields=['application']),
            models.Index(fields=['student']),
            models.Index(fields=['offered_class']),
            models.Index(fields=['offer_expires']),
            models.Index(fields=['accepted']),
            models.Index(fields=['enrollment_deadline']),
            models.Index(fields=['acceptance_fee_deadline']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Admission {self.admission_number} - {self.student.full_name}"
    
    def clean(self):
        """Validate admission data."""
        from django.core.exceptions import ValidationError
        
        # Validate application and student consistency
        if self.application and self.student and self.application.student != self.student:
            raise ValidationError({
                'student': 'Student must match the application student.'
            })
        
        # Validate offered class belongs to same school
        if self.offered_class and self.student and self.offered_class.school != self.student.school:
            raise ValidationError({
                'offered_class': 'Offered class must belong to the same school as the student.'
            })
        
        # Validate dates
        if self.offer_expires and self.offer_expires <= timezone.now():
            raise ValidationError({
                'offer_expires': 'Offer expiration must be in the future.'
            })
        
        if self.enrollment_deadline and self.enrollment_deadline <= timezone.now():
            raise ValidationError({
                'enrollment_deadline': 'Enrollment deadline must be in the future.'
            })
        
        if self.acceptance_fee_deadline and self.acceptance_fee_deadline <= timezone.now():
            raise ValidationError({
                'acceptance_fee_deadline': 'Acceptance fee deadline must be in the future.'
            })
        
        # Validate offered class capacity using shared manager
        from shared.models import ClassManager
        if self.offered_class:
            is_available, message, _ = ClassManager.validate_class_availability(
                self.offered_class.id,
                self.student.school,
                is_staff=self.application.is_staff_child if self.application else False
            )
            if not is_available:
                raise ValidationError({
                    'offered_class': f'Class "{self.offered_class.name}" {message}.'
                })
    
    def save(self, *args, **kwargs):
        """Save admission with auto-generated number and defaults."""
        self.full_clean()  # Run validation first
        
        # Generate admission number if not provided
        if not self.admission_number:
            self.admission_number = self.generate_admission_number()
        
        # Set default expiration (2 weeks) if not provided
        if not self.offer_expires:
            self.offer_expires = timezone.now() + timezone.timedelta(days=14)
        
        # Set acceptance fee deadline if applicable
        if self.requires_acceptance_fee and not self.acceptance_fee_deadline:
            self.acceptance_fee_deadline = timezone.now() + timezone.timedelta(days=7)
        
        # Set enrollment deadline if not provided
        if not self.enrollment_deadline:
            self.enrollment_deadline = timezone.now() + timezone.timedelta(days=30)
        
        # Auto-mark as enrolled if all requirements met
        if self.can_complete_enrollment() and not self.enrollment_completed:
            self.enrollment_completed = True
            self.enrollment_completed_at = timezone.now()
            
            # Update student's current class
            if self.offered_class:
                self.student.current_class = self.offered_class
                self.student.admission_status = 'enrolled'
                self.student.save(update_fields=['current_class', 'admission_status'])
        
        super().save(*args, **kwargs)
    
    def generate_admission_number(self):
        """Generate unique admission number."""
        school_code = self.student.school.subdomain.upper()[:3] if self.student.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        unique_id = str(uuid.uuid4().int)[:6].upper()
        return f"ADM/{school_code}/{year}/{unique_id}"
    
    @property
    def is_offer_expired(self):
        """Check if admission offer has expired."""
        return timezone.now() > self.offer_expires
    
    @property
    def days_until_expiry(self):
        """Get days until offer expires."""
        if self.is_offer_expired:
            return 0
        delta = (self.offer_expires - timezone.now()).days
        return max(0, delta)
    
    @property
    def days_until_enrollment_deadline(self):
        """Get days until enrollment deadline."""
        if self.enrollment_completed or not self.enrollment_deadline:
            return None
        delta = (self.enrollment_deadline - timezone.now()).days
        return max(0, delta)
    
    @property
    def is_enrollment_overdue(self):
        """Check if enrollment is overdue."""
        if self.enrollment_completed or not self.enrollment_deadline:
            return False
        return timezone.now() > self.enrollment_deadline
    
    @property
    def admission_progress(self):
        """Calculate admission completion progress (0-100)."""
        steps_completed = 0
        total_steps = 5  # offer, acceptance, fee, docs, enrollment
        
        if self.accepted:
            steps_completed += 1
        if self.acceptance_fee_paid or not self.requires_acceptance_fee:
            steps_completed += 1
        if self.required_documents_submitted:
            steps_completed += 1
        if self.documents_verified:
            steps_completed += 1
        if self.enrollment_completed:
            steps_completed += 1
        
        return int((steps_completed / total_steps) * 100)
    
    def can_complete_enrollment(self):
        """Check if all enrollment requirements are met."""
        return (
            self.accepted and 
            (self.acceptance_fee_paid or not self.requires_acceptance_fee) and
            self.required_documents_submitted and 
            self.documents_verified and
            not self.enrollment_completed
        )
    
    def send_admission_letter(self, method='email'):
        """Send admission letter via specified method."""
        # This would integrate with email/SMS services
        self.admission_letter_sent = True
        self.admission_letter_sent_at = timezone.now()
        self.admission_letter_method = method
        self.save()
        
        logger.info(f"Admission letter sent via {method} for {self.admission_number}")
        return True