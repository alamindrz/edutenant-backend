# attendance/signals.py
import logging
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError



# ✅ Import shared constants
from shared.constants import StatusChoices

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name, app_label):
    """Safe model import to avoid circular dependencies."""
    from django.apps import apps
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def _calculate_week_range(date):
    """Calculate start and end dates for a week containing the given date."""
    start_of_week = date - timedelta(days=date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week


# ============ STUDENT ATTENDANCE SIGNALS ============

@receiver(post_save, sender='attendance.StudentAttendance')
def update_student_attendance_summary(sender, instance, created, **kwargs):
    """
    Update attendance summary when new student attendance records are added.
    Uses shared constants and safe imports.
    """
    try:
        # ✅ Use string reference to avoid circular import
        AttendanceSummary = _get_model('AttendanceSummary', 'attendance')

        # Calculate week range
        start_of_week, end_of_week = _calculate_week_range(instance.date)

        # Get or create weekly summary
        summary, summary_created = AttendanceSummary.objects.get_or_create(
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
                'attendance_rate': 0,
                'punctuality_rate': 0,
            }
        )

        # Recalculate all counts for accuracy
        attendance_records = instance.__class__.objects.filter(
            student=instance.student,
            academic_term=instance.academic_term,
            date__range=[start_of_week, end_of_week]
        )

        # ✅ Use shared constants
        summary.total_days = attendance_records.count()
        summary.days_present = attendance_records.filter(
            status=StatusChoices.PRESENT
        ).count()
        summary.days_absent = attendance_records.filter(
            status=StatusChoices.ABSENT
        ).count()
        summary.days_late = attendance_records.filter(
            status=StatusChoices.LATE
        ).count()
        summary.days_excused = attendance_records.filter(
            status='excused'
        ).count()  # This one might need to be added to shared constants

        # Recalculate rates
        summary.calculate_rates()
        summary.save(update_fields=[
            'total_days', 'days_present', 'days_absent',
            'days_late', 'days_excused', 'attendance_rate',
            'punctuality_rate', 'updated_at'
        ])

        logger.debug(f"Updated attendance summary for {instance.student.full_name} (Week {start_of_week})")

        # ✅ Also update monthly summary
        _update_monthly_student_summary(instance)

    except Exception as e:
        logger.error(f"Error updating attendance summary for {instance.student_id}: {str(e)}", exc_info=True)


def _update_monthly_student_summary(instance):
    """Update monthly attendance summary for student."""
    try:
        AttendanceSummary = _get_model('AttendanceSummary', 'attendance')

        # Calculate month range
        start_of_month = instance.date.replace(day=1)
        if start_of_month.month == 12:
            end_of_month = start_of_month.replace(year=start_of_month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = start_of_month.replace(month=start_of_month.month + 1, day=1) - timedelta(days=1)

        # Get or create monthly summary
        summary, created = AttendanceSummary.objects.get_or_create(
            student=instance.student,
            academic_term=instance.academic_term,
            period_type='monthly',
            start_date=start_of_month,
            end_date=end_of_month,
            defaults={
                'total_days': 0,
                'days_present': 0,
                'days_absent': 0,
                'days_late': 0,
                'days_excused': 0,
                'attendance_rate': 0,
                'punctuality_rate': 0,
            }
        )

        # Recalculate counts
        attendance_records = instance.__class__.objects.filter(
            student=instance.student,
            academic_term=instance.academic_term,
            date__range=[start_of_month, end_of_month]
        )

        # ✅ Use shared constants
        summary.total_days = attendance_records.count()
        summary.days_present = attendance_records.filter(
            status=StatusChoices.PRESENT
        ).count()
        summary.days_absent = attendance_records.filter(
            status=StatusChoices.ABSENT
        ).count()
        summary.days_late = attendance_records.filter(
            status=StatusChoices.LATE
        ).count()
        summary.days_excused = attendance_records.filter(
            status='excused'
        ).count()

        summary.calculate_rates()
        summary.save()

        logger.debug(f"Updated monthly summary for {instance.student.full_name} ({start_of_month.strftime('%B %Y')})")

    except Exception as e:
        logger.error(f"Error updating monthly summary: {str(e)}", exc_info=True)


# ============ TEACHER ATTENDANCE SIGNALS ============

@receiver(post_save, sender='attendance.TeacherAttendance')
def update_teacher_performance(sender, instance, created, **kwargs):
    """
    Update teacher performance when attendance records change.
    Uses shared constants and safe imports.
    """
    try:
        # ✅ Use string reference to avoid circular import
        TeacherPerformance = _get_model('TeacherPerformance', 'attendance')

        if instance.sign_in_time and instance.sign_out_time:
            # Calculate week range
            start_of_week, end_of_week = _calculate_week_range(instance.date)

            # Get or create weekly performance record
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
                    'attendance_score': 0,
                    'punctuality_score': 0,
                    'overall_performance': 0,
                }
            )

            # Recalculate all metrics for accuracy
            attendance_records = instance.__class__.objects.filter(
                staff=instance.staff,
                academic_term=instance.academic_term,
                date__range=[start_of_week, end_of_week],
                sign_in_time__isnull=False
            )

            # ✅ Use shared constants
            performance.total_work_days = attendance_records.count()
            performance.days_present = attendance_records.filter(
                status=StatusChoices.PRESENT
            ).count()
            performance.days_absent = attendance_records.filter(
                status=StatusChoices.ABSENT
            ).count()
            performance.days_late = attendance_records.filter(
                is_late=True
            ).count()

            # Calculate average work hours
            total_hours = 0
            work_days = 0
            for record in attendance_records:
                if hasattr(record, 'work_duration_minutes'):
                    minutes = record.work_duration_minutes
                    if minutes and minutes > 0:
                        total_hours += minutes / 60
                        work_days += 1

            performance.average_work_hours = total_hours / work_days if work_days > 0 else 0

            performance.calculate_scores()
            performance.save()

            logger.debug(f"Updated performance record for {instance.staff.full_name} (Week {start_of_week})")

            # ✅ Also update monthly performance
            _update_monthly_teacher_performance(instance)

    except Exception as e:
        logger.error(f"Error updating teacher performance for {instance.staff_id}: {str(e)}", exc_info=True)


def _update_monthly_teacher_performance(instance):
    """Update monthly teacher performance."""
    try:
        TeacherPerformance = _get_model('TeacherPerformance', 'attendance')

        # Calculate month range
        start_of_month = instance.date.replace(day=1)
        if start_of_month.month == 12:
            end_of_month = start_of_month.replace(year=start_of_month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = start_of_month.replace(month=start_of_month.month + 1, day=1) - timedelta(days=1)

        # Get or create monthly performance
        performance, created = TeacherPerformance.objects.get_or_create(
            staff=instance.staff,
            academic_term=instance.academic_term,
            period_type='monthly',
            start_date=start_of_month,
            end_date=end_of_month,
            defaults={
                'total_work_days': 0,
                'days_present': 0,
                'days_absent': 0,
                'days_late': 0,
                'average_work_hours': 0,
                'attendance_score': 0,
                'punctuality_score': 0,
                'overall_performance': 0,
            }
        )

        # Recalculate metrics
        attendance_records = instance.__class__.objects.filter(
            staff=instance.staff,
            academic_term=instance.academic_term,
            date__range=[start_of_month, end_of_month],
            sign_in_time__isnull=False
        )

        # ✅ Use shared constants
        performance.total_work_days = attendance_records.count()
        performance.days_present = attendance_records.filter(
            status=StatusChoices.PRESENT
        ).count()
        performance.days_absent = attendance_records.filter(
            status=StatusChoices.ABSENT
        ).count()
        performance.days_late = attendance_records.filter(
            is_late=True
        ).count()

        # Calculate average work hours
        total_hours = 0
        work_days = 0
        for record in attendance_records:
            if hasattr(record, 'work_duration_minutes'):
                minutes = record.work_duration_minutes
                if minutes and minutes > 0:
                    total_hours += minutes / 60
                    work_days += 1

        performance.average_work_hours = total_hours / work_days if work_days > 0 else 0

        performance.calculate_scores()
        performance.save()

        logger.debug(f"Updated monthly performance for {instance.staff.full_name} ({start_of_month.strftime('%B %Y')})")

    except Exception as e:
        logger.error(f"Error updating monthly teacher performance: {str(e)}", exc_info=True)


# ============ NOTIFICATION SIGNALS ============

@receiver(post_save, sender='attendance.StudentAttendance')
def notify_on_student_absence(sender, instance, created, **kwargs):
    """Send notifications for student absences."""
    try:
        # Only notify for new absences
        if created and instance.status == StatusChoices.ABSENT:
            # Check attendance config
            try:
                # Get school's attendance config
                school = instance.academic_term.school
                if hasattr(school, 'attendance_config'):
                    config = school.attendance_config

                    # Only send if configured
                    if config and config.send_absent_notifications:
                        logger.info(f"Student absence notification triggered for {instance.student.full_name}")

                        # ✅ Check for consecutive absences
                        consecutive_count = _count_consecutive_absences(instance)
                        if consecutive_count >= 3:  # Threshold for urgent notification
                            logger.warning(f"Student {instance.student.full_name} has {consecutive_count} consecutive absences")

                        # TODO: Send actual notification (email/SMS)
                        # notification_service.send_absence_notification(instance)

            except AttributeError:
                logger.warning("No attendance config found for school")

    except Exception as e:
        logger.error(f"Error in absence notification: {str(e)}", exc_info=True)


def _count_consecutive_absences(attendance_record):
    """Count consecutive absences for a student."""
    try:
        count = 1  # Start with current absence
        current_date = attendance_record.date

        # Check previous days
        previous_day = current_date - timedelta(days=1)
        while True:
            previous_attendance = attendance_record.__class__.objects.filter(
                student=attendance_record.student,
                date=previous_day,
                status=StatusChoices.ABSENT
            ).first()

            if previous_attendance:
                count += 1
                previous_day -= timedelta(days=1)
            else:
                break

        return count

    except Exception as e:
        logger.error(f"Error counting consecutive absences: {str(e)}")
        return 1


@receiver(post_save, sender='attendance.TeacherAttendance')
def notify_on_teacher_tardiness(sender, instance, created, **kwargs):
    """Send notifications for teacher tardiness."""
    try:
        if created and instance.is_late:
            # Check attendance config
            try:
                school = instance.academic_term.school
                if hasattr(school, 'attendance_config'):
                    config = school.attendance_config

                    # Only send if configured
                    if config and config.notify_on_late_teachers:
                        logger.info(f"Teacher tardiness notification triggered for {instance.staff.full_name}")

                        # TODO: Send actual notification
                        # notification_service.send_tardiness_notification(instance)

            except AttributeError:
                logger.warning("No attendance config found for school")

    except Exception as e:
        logger.error(f"Error in tardiness notification: {str(e)}", exc_info=True)


# ============ DATA VALIDATION SIGNALS ============

@receiver(pre_save, sender='attendance.StudentAttendance')
def validate_student_attendance(sender, instance, **kwargs):
    """Validate student attendance data before saving."""
    try:
        # Check for duplicate attendance on same date
        if instance.pk:  # Existing record
            duplicates = sender.objects.filter(
                student=instance.student,
                date=instance.date
            ).exclude(pk=instance.pk)
        else:  # New record
            duplicates = sender.objects.filter(
                student=instance.student,
                date=instance.date
            )

        if duplicates.exists():
            raise ValidationError(
                f"Attendance already recorded for {instance.student.full_name} on {instance.date}"
            )

        # Validate date not in future
        if instance.date > timezone.now().date():
            raise ValidationError("Cannot record attendance for future dates.")

    except Exception as e:
        logger.error(f"Error validating student attendance: {str(e)}")
        raise


@receiver(pre_save, sender='attendance.TeacherAttendance')
def validate_teacher_attendance(sender, instance, **kwargs):
    """Validate teacher attendance data before saving."""
    try:
        # Check for duplicate attendance on same date
        if instance.pk:  # Existing record
            duplicates = sender.objects.filter(
                staff=instance.staff,
                date=instance.date
            ).exclude(pk=instance.pk)
        else:  # New record
            duplicates = sender.objects.filter(
                staff=instance.staff,
                date=instance.date
            )

        if duplicates.exists():
            raise ValidationError(
                f"Attendance already recorded for {instance.staff.full_name} on {instance.date}"
            )

        # Validate date not in future
        if instance.date > timezone.now().date():
            raise ValidationError("Cannot record attendance for future dates.")

    except Exception as e:
        logger.error(f"Error validating teacher attendance: {str(e)}")
        raise


# ============ CLEANUP SIGNALS ============

@receiver(post_delete, sender='attendance.StudentAttendance')
def cleanup_student_summaries(sender, instance, **kwargs):
    """Clean up attendance summaries when records are deleted."""
    try:
        AttendanceSummary = _get_model('AttendanceSummary', 'attendance')

        # Delete related summaries if they become empty
        summaries = AttendanceSummary.objects.filter(
            student=instance.student,
            academic_term=instance.academic_term
        )

        for summary in summaries:
            # Check if summary has any attendance records
            attendance_count = instance.__class__.objects.filter(
                student=instance.student,
                academic_term=instance.academic_term,
                date__range=[summary.start_date, summary.end_date]
            ).count()

            if attendance_count == 0:
                summary.delete()
                logger.debug(f"Deleted empty attendance summary for {instance.student.full_name}")

    except Exception as e:
        logger.error(f"Error cleaning up student summaries: {str(e)}", exc_info=True)


# ============ SIGNAL CONNECTIONS ============

def connect_attendance_signals():
    """Explicitly connect all attendance signals."""
    # These are automatically connected via @receiver decorators,
    # but this function provides explicit control if needed
    pass
