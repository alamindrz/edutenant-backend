# admissions/signals.py - ENHANCED
import logging
from django.db.models.signals import post_save, pre_save, m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.core.cache import cache

from .models import Application, Admission, ApplicationForm
from students.models import Student

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Application)
def handle_application_status_change(sender, instance, created, **kwargs):
    """Enhanced application status change handling."""
    if not created:
        try:
            old_instance = Application.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                logger.info(f"Application {instance.application_number} status changed: {old_instance.status} -> {instance.status}")
                
                # Update form application count
                if instance.status == 'submitted':
                    instance.form.applications_so_far += 1
                    instance.form.save()
                
                # Create student record when application is accepted
                if instance.status == 'accepted' and not instance.student:
                    student_data = {
                        'school': instance.form.school,
                        'first_name': instance.data.get('first_name', ''),
                        'last_name': instance.data.get('last_name', ''),
                        'gender': instance.data.get('gender', ''),
                        'date_of_birth': instance.data.get('date_of_birth'),
                        'parent': instance.parent,
                        'education_level': instance.applied_class.education_level if instance.applied_class else None,
                        'class_group': instance.applied_class,
                        'admission_status': 'accepted',
                        'application_date': timezone.now()
                    }
                    instance.student = Student.objects.create(**student_data)
                    instance.save()
                    logger.info(f"Student record created: {instance.student.full_name}")
                
                # Invalidate cache
                cache.delete(f'school_{instance.form.school.id}_admission_stats')
                
        except Application.DoesNotExist:
            pass

@receiver(post_save, sender=Admission)
def handle_admission_acceptance(sender, instance, created, **kwargs):
    """Enhanced admission acceptance handling."""
    if instance.accepted and not created:
        try:
            # Update student status to enrolled when enrollment is completed
            if instance.enrollment_completed:
                instance.student.admission_status = 'enrolled'
                instance.student.is_active = True
                instance.student.enrollment_date = timezone.now()
                instance.student.save()
                
                logger.info(f"Student {instance.student.full_name} officially enrolled")
            
        except Exception as e:
            logger.error(f"Error handling admission acceptance: {str(e)}")

@receiver(pre_save, sender=ApplicationForm)
def validate_application_form_dates(sender, instance, **kwargs):
    """Enhanced form validation."""
    if instance.open_date and instance.close_date:
        if instance.open_date >= instance.close_date:
            raise ValueError("Close date must be after open date")
    
    # Auto-close forms after close date
    if instance.close_date and instance.close_date < timezone.now():
        instance.status = 'closed'
    
    # Auto-pause forms that reach max applications
    if (instance.max_applications and 
        instance.applications_so_far >= instance.max_applications and
        instance.status == 'active'):
        instance.status = 'paused'
        logger.info(f"Application form {instance.name} paused - reached max applications")

@receiver(pre_save, sender=Admission)
def validate_admission_dates(sender, instance, **kwargs):
    """Validate admission dates and deadlines."""
    if instance.offer_expires and instance.offer_expires < timezone.now():
        raise ValueError("Offer expiration date cannot be in the past")
    
    if instance.enrollment_deadline and instance.enrollment_deadline < timezone.now():
        raise ValueError("Enrollment deadline cannot be in the past") 