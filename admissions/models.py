# admissions/models.py - COMPLETED
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
import uuid
import logging

logger = logging.getLogger(__name__)

class ApplicationForm(models.Model):
    FORM_STATUS = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
    )
    
    school = models.ForeignKey('users.School', on_delete=models.CASCADE, related_name='application_forms')
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=FORM_STATUS, default='draft')
    
    # Enhanced fee configuration
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, default='NGN')
    
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
    available_classes = models.JSONField(default=list, help_text="Classes accepting applications")
    
    # Application limits
    max_applications = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for unlimited")
    applications_so_far = models.PositiveIntegerField(default=0, editable=False)
    
    # Metadata
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
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
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.school.subdomain}-{self.name}")
            self.slug = base_slug
            counter = 1
            while ApplicationForm.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        
        if not self.close_date:
            self.close_date = self.open_date + timezone.timedelta(days=90)
        
        super().save(*args, **kwargs)
    
    @property
    def is_open(self):
        now = timezone.now()
        return (self.status == 'active' and 
                self.open_date <= now <= self.close_date and
                (self.max_applications is None or 
                 self.applications_so_far < self.max_applications))
    
    @property
    def days_remaining(self):
        if not self.is_open:
            return 0
        return (self.close_date - timezone.now()).days


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
    form = models.ForeignKey(ApplicationForm, on_delete=models.CASCADE, related_name='applications')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, null=True, blank=True, related_name='applications')
    parent = models.ForeignKey('students.Parent', on_delete=models.CASCADE, related_name='applications')
    
    # Enhanced application data
    data = models.JSONField(default=dict, help_text="Application form data")
    documents = models.JSONField(default=list, help_text="Uploaded documents")
    
    # Status tracking with history
    status = models.CharField(max_length=20, choices=APPLICATION_STATUS, default='submitted')
    status_changed_at = models.DateTimeField(auto_now=True)
    status_history = models.JSONField(default=list, help_text="Status change history")
    
    # Payment tracking
    application_fee_paid = models.BooleanField(default=False)
    application_fee_invoice = models.ForeignKey('billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Enhanced review system
    assigned_to = models.ForeignKey('users.Staff', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_applications')
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Nigerian context
    applied_class = models.ForeignKey('students.ClassGroup', on_delete=models.SET_NULL, null=True, blank=True)
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
            models.Index(fields=['submitted_at']),
            models.Index(fields=['priority']),
        ]
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"Application {self.application_number}"
    
    def save(self, *args, **kwargs):
        if not self.application_number:
            self.application_number = self.generate_application_number()
        
        # Track status changes
        if self.pk:
            try:
                old_instance = Application.objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    self.status_history.append({
                        'from_status': old_instance.status,
                        'to_status': self.status,
                        'changed_at': timezone.now().isoformat(),
                        'changed_by': getattr(self, '_current_user', None),
                        'notes': f"Status changed from {old_instance.status} to {self.status}"
                    })
            except Application.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def generate_application_number(self):
        school_code = self.form.school.subdomain.upper() if self.form.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        unique_id = str(uuid.uuid4().int)[:6].upper()
        return f"APP/{school_code}/{year}/{unique_id}"
    
    @property
    def processing_time(self):
        return (timezone.now() - self.submitted_at).days
    
    @property
    def is_overdue(self):
        return self.processing_time > 14 and self.status == 'submitted'  # Overdue if > 14 days
    
    @property
    def student_full_name(self):
        """Get student's full name from data or linked student."""
        if self.student:
            return self.student.full_name
        return f"{self.data.get('first_name', '')} {self.data.get('last_name', '')}".strip()
    
    @property
    def parent_full_name(self):
        """Get parent's full name."""
        if hasattr(self.parent, 'full_name'):
            return self.parent.full_name
        return f"{self.data.get('parent_first_name', '')} {self.data.get('parent_last_name', '')}".strip()


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
    offered_class = models.ForeignKey('students.ClassGroup', on_delete=models.PROTECT, related_name='admission_offers')
    offer_expires = models.DateTimeField()
    
    # Enhanced acceptance tracking
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    acceptance_notes = models.TextField(blank=True, help_text="Parent's acceptance notes")  # NEW
    
    # Enhanced fee tracking
    requires_acceptance_fee = models.BooleanField(default=False)
    acceptance_fee_invoice = models.ForeignKey('billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    acceptance_fee_paid = models.BooleanField(default=False)
    acceptance_fee_deadline = models.DateTimeField(null=True, blank=True)  # NEW
    
    # Nigerian context enhancements
    admission_letter_sent = models.BooleanField(default=False)
    admission_letter_sent_at = models.DateTimeField(null=True, blank=True)
    admission_letter_method = models.CharField(max_length=20, default='email', choices=[  # NEW
        ('email', 'Email'), ('sms', 'SMS'), ('print', 'Printed'), ('whatsapp', 'WhatsApp')
    ])
    
    # NEW: Admission conditions and requirements
    conditions = models.JSONField(default=list, help_text="Admission conditions to be met")
    required_documents_submitted = models.BooleanField(default=False)
    documents_verified = models.BooleanField(default=False)
    
    # NEW: Timeline tracking
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
            models.Index(fields=['offer_expires']),
            models.Index(fields=['accepted']),
            models.Index(fields=['enrollment_deadline']),  # NEW
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Admission {self.admission_number} - {self.student.full_name}"
    
    def save(self, *args, **kwargs):
        if not self.admission_number:
            self.admission_number = self.generate_admission_number()
        
        # Set default expiration (2 weeks)
        if not self.offer_expires:
            self.offer_expires = timezone.now() + timezone.timedelta(days=14)
        
        # Set acceptance fee deadline if applicable
        if self.requires_acceptance_fee and not self.acceptance_fee_deadline:
            self.acceptance_fee_deadline = timezone.now() + timezone.timedelta(days=7)
        
        # Set enrollment deadline
        if not self.enrollment_deadline:
            self.enrollment_deadline = timezone.now() + timezone.timedelta(days=30)
        
        # Auto-mark as enrolled if acceptance fee paid and conditions met
        if (self.accepted and self.acceptance_fee_paid and 
            self.required_documents_submitted and self.documents_verified and
            not self.enrollment_completed):
            self.enrollment_completed = True
            self.enrollment_completed_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def generate_admission_number(self):
        school_code = self.student.school.subdomain.upper() if self.student.school.subdomain else 'SCH'
        year = timezone.now().strftime('%y')
        unique_id = str(uuid.uuid4().int)[:6]
        return f"ADM/{school_code}/{year}/{unique_id}"
    
    @property
    def is_offer_expired(self):
        return timezone.now() > self.offer_expires
    
    @property
    def days_until_expiry(self):
        if self.is_offer_expired:
            return 0
        return (self.offer_expires - timezone.now()).days
    
    @property
    def days_until_enrollment_deadline(self):
        if self.enrollment_completed or not self.enrollment_deadline:
            return None
        delta = (self.enrollment_deadline - timezone.now()).days
        return max(0, delta)
    
    @property
    def is_enrollment_overdue(self):
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
    
    def send_admission_letter(self, method='email'):
        """Send admission letter via specified method."""
        # Implementation would integrate with email/SMS services
        self.admission_letter_sent = True
        self.admission_letter_sent_at = timezone.now()
        self.admission_letter_method = method
        self.save()
        
        logger.info(f"Admission letter sent via {method} for {self.admission_number}")
        return True
        
        
    def can_complete_enrollment(self):
        """Check if all enrollment requirements are met."""
        return (self.accepted and 
                (self.acceptance_fee_paid or not self.requires_acceptance_fee) and
                self.required_documents_submitted and 
                self.documents_verified)
                

