# attendance/signals.py - FIXED
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import StudentAttendance, TeacherAttendance, AttendanceSummary, TeacherPerformance
from students.models import AcademicTerm

logger = logging.getLogger(__name__)

@receiver(post_save, sender=StudentAttendance)
def update_student_attendance_summary(sender, instance, created, **kwargs):
    """Update attendance summary when new records are added."""
    try:
        # Get or create weekly summary
        start_of_week = instance.date - timedelta(days=instance.date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        summary, created = AttendanceSummary.objects.get_or_create(
            student=instance.student,
            academic_term=instance.academic_term,
            period_type='weekly',
            start_date=start_of_week,
            end_date=end_of_week,
            defaults={
                'total_days': 0,
                'days_present': 0,
                'days_absent': 0,
                'days_late': 0,
                'days_excused': 0,
            }
        )
        
        # Recalculate all counts for accuracy
        attendance_records = StudentAttendance.objects.filter(
            student=instance.student,
            academic_term=instance.academic_term,
            date__range=[start_of_week, end_of_week]
        )
        
        summary.total_days = attendance_records.count()
        summary.days_present = attendance_records.filter(status='present').count()
        summary.days_absent = attendance_records.filter(status='absent').count()
        summary.days_late = attendance_records.filter(status='late').count()
        summary.days_excused = attendance_records.filter(status='excused').count()
        
        summary.calculate_rates()
        summary.save()
        
        logger.info(f"Updated attendance summary for {instance.student.full_name}")
        
    except Exception as e:
        logger.error(f"Error updating attendance summary: {str(e)}")

@receiver(post_save, sender=TeacherAttendance)
def update_teacher_performance(sender, instance, created, **kwargs):
    """Update teacher performance when attendance records change."""
    try:
        if instance.sign_in_time and instance.sign_out_time:
            # Get or create weekly performance record
            start_of_week = instance.date - timedelta(days=instance.date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            
            performance, created = TeacherPerformance.objects.get_or_create(
                staff=instance.staff,
                academic_term=instance.academic_term,
                period_type='weekly',
                start_date=start_of_week,
                end_date=end_of_week,
                defaults={
                    'total_work_days': 0,
                    'days_present': 0,
                    'days_absent': 0,
                    'days_late': 0,
                    'average_work_hours': 0,
                }
            )
            
            # Recalculate all metrics for accuracy
            attendance_records = TeacherAttendance.objects.filter(
                staff=instance.staff,
                academic_term=instance.academic_term,
                date__range=[start_of_week, end_of_week],
                sign_in_time__isnull=False
            )
            
            performance.total_work_days = attendance_records.count()
            performance.days_present = attendance_records.filter(status='present').count()
            performance.days_absent = attendance_records.filter(status='absent').count()
            performance.days_late = attendance_records.filter(is_late=True).count()
            
            # Calculate average work hours
            total_hours = sum(record.work_duration_minutes / 60 for record in attendance_records if record.work_duration_minutes)
            performance.average_work_hours = total_hours / performance.total_work_days if performance.total_work_days > 0 else 0
            
            performance.calculate_scores()
            performance.save()
            
            logger.info(f"Updated performance record for {instance.staff.full_name}")
            
    except Exception as e:
        logger.error(f"Error updating teacher performance: {str(e)}")