# attendance/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging
from datetime import datetime, time as time_type

logger = logging.getLogger(__name__)


class AttendanceConfig(models.Model):
    """School-specific attendance configuration."""
    SCHOOL_SESSION_TYPES = (
        ('single', 'Single Session'),
        ('double', 'Double Session'),
    )

    # ✅ FIXED: Use 'core.School' instead of 'users.School'
    school = models.OneToOneField('core.School', on_delete=models.CASCADE, related_name='attendance_config')
    session_type = models.CharField(max_length=10, choices=SCHOOL_SESSION_TYPES, default='single')

    # Student attendance settings
    student_marking_enabled = models.BooleanField(default=True)
    auto_mark_absent = models.BooleanField(default=True)
    late_threshold_minutes = models.IntegerField(default=30)
    early_departure_minutes = models.IntegerField(default=60)

    # Teacher attendance settings
    teacher_attendance_enabled = models.BooleanField(default=True)
    teacher_signin_required = models.BooleanField(default=True)
    teacher_late_threshold = models.IntegerField(default=15)  # minutes

    # School hours
    school_start_time = models.TimeField(default='08:00:00')
    school_end_time = models.TimeField(default='14:00:00')
    break_start_time = models.TimeField(null=True, blank=True)
    break_end_time = models.TimeField(null=True, blank=True)

    # Notifications
    send_absent_notifications = models.BooleanField(default=True)
    notify_on_late_teachers = models.BooleanField(default=True)

    class Meta:
        db_table = 'attendance_config'
        verbose_name = 'Attendance Configuration'
        verbose_name_plural = 'Attendance Configurations'

    def __str__(self):
        return f"Attendance Config - {self.school.name}"

    def clean(self):
        """Validate time settings."""
        if self.school_start_time >= self.school_end_time:
            raise ValidationError("School end time must be after start time.")

        if self.break_start_time and self.break_end_time:
            if self.break_start_time >= self.break_end_time:
                raise ValidationError("Break end time must be after start time.")

            if (self.break_start_time < self.school_start_time or
                self.break_end_time > self.school_end_time):
                raise ValidationError("Break times must be within school hours.")


class StudentAttendance(models.Model):
    """Student attendance records."""
    # ✅ Consider moving to shared constants if used elsewhere
    ATTENDANCE_STATUS = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused Absence'),
        ('sick', 'Sick Leave'),
        ('other', 'Other'),
    )

    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='attendance_records')
    academic_term = models.ForeignKey('students.AcademicTerm', on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default='present')

    # Time tracking for detailed attendance
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)

    # Additional information
    remarks = models.TextField(blank=True)
    is_late = models.BooleanField(default=False)
    early_departure = models.BooleanField(default=False)

    # Metadata
    # ✅ FIXED: Use 'users.Profile' or 'core.User' - check your actual model
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_student_attendance'
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance_student'
        verbose_name = 'Student Attendance'
        verbose_name_plural = 'Student Attendance Records'
        unique_together = ['student', 'date']
        indexes = [
            models.Index(fields=['student', 'date']),
            models.Index(fields=['academic_term', 'date']),
            models.Index(fields=['date', 'status']),
        ]
        ordering = ['-date', 'student']

    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"

    def clean(self):
        """Validate attendance data."""
        if self.time_in and self.time_out and self.time_in >= self.time_out:
            raise ValidationError("Time out must be after time in.")

        if self.date > timezone.now().date():
            raise ValidationError("Cannot record attendance for future dates.")

        # ✅ Validate student belongs to same school as academic term
        if self.student.school != self.academic_term.school:
            raise ValidationError("Student must belong to the same school as academic term.")

    def save(self, *args, **kwargs):
        """Calculate late and early departure status."""
        # ✅ Added proper error handling and existence checks
        if self.time_in and self.academic_term:
            try:
                # Get school from academic_term
                school = self.academic_term.school
                if hasattr(school, 'attendance_config') and school.attendance_config:
                    config = school.attendance_config
                    school_start = datetime.combine(self.date, config.school_start_time)
                    time_in_dt = datetime.combine(self.date, self.time_in)

                    # Check if late
                    time_diff = (time_in_dt - school_start).total_seconds() / 60  # minutes
                    self.is_late = time_diff > config.late_threshold_minutes
            except AttributeError as e:
                logger.warning(f"Error accessing attendance config: {e}")
            except Exception as e:
                logger.warning(f"Error calculating late status: {e}")

        if self.time_out and self.academic_term:
            try:
                school = self.academic_term.school
                if hasattr(school, 'attendance_config') and school.attendance_config:
                    config = school.attendance_config
                    school_end = datetime.combine(self.date, config.school_end_time)
                    time_out_dt = datetime.combine(self.date, self.time_out)

                    # Check if early departure
                    time_diff = (school_end - time_out_dt).total_seconds() / 60  # minutes
                    self.early_departure = time_diff > config.early_departure_minutes
            except Exception as e:
                logger.warning(f"Error calculating early departure: {e}")

        super().save(*args, **kwargs)

    @property
    def duration_minutes(self):
        """Calculate attendance duration in minutes."""
        if self.time_in and self.time_out:
            try:
                time_in_dt = datetime.combine(self.date, self.time_in)
                time_out_dt = datetime.combine(self.date, self.time_out)
                return (time_out_dt - time_in_dt).total_seconds() / 60
            except Exception as e:
                logger.warning(f"Error calculating duration: {e}")
        return 0

    @property
    def student_class(self):
        """Get the student's current class."""
        # ✅ Using shared ClassManager or direct attribute
        return getattr(self.student, 'current_class', None)

    @property
    def class_name(self):
        """Get the student's class name."""
        class_obj = self.student_class
        if class_obj and hasattr(class_obj, 'name'):
            return class_obj.name
        return "No Class Assigned"


class TeacherAttendance(models.Model):
    """Teacher attendance and sign-in/out records."""
    ATTENDANCE_STATUS = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half_day', 'Half Day'),
        ('leave', 'On Leave'),
        ('other', 'Other'),
    )

    # ✅ FIXED: Use 'users.Staff' - make sure this model exists
    staff = models.ForeignKey('users.Staff', on_delete=models.CASCADE, related_name='attendance_records')
    academic_term = models.ForeignKey('students.AcademicTerm', on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default='present')

    # Sign-in/out tracking
    sign_in_time = models.DateTimeField(null=True, blank=True)
    sign_out_time = models.DateTimeField(null=True, blank=True)

    # Location tracking (optional)
    sign_in_location = models.CharField(max_length=255, blank=True)
    sign_out_location = models.CharField(max_length=255, blank=True)

    # Additional information
    remarks = models.TextField(blank=True)
    is_late = models.BooleanField(default=False)
    auto_signed_out = models.BooleanField(default=False)

    # Recorded by (principal or staff manager)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_teacher_attendance'
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance_teacher'
        verbose_name = 'Teacher Attendance'
        verbose_name_plural = 'Teacher Attendance Records'
        unique_together = ['staff', 'date']
        indexes = [
            models.Index(fields=['staff', 'date']),
            models.Index(fields=['academic_term', 'date']),
            models.Index(fields=['date', 'status']),
            models.Index(fields=['sign_in_time']),
        ]
        ordering = ['-date', 'staff']

    def __str__(self):
        return f"{self.staff} - {self.date} - {self.status}"

    def clean(self):
        """Validate teacher attendance data."""
        if self.sign_in_time and self.sign_out_time and self.sign_in_time >= self.sign_out_time:
            raise ValidationError("Sign out time must be after sign in time.")

        if self.date > timezone.now().date():
            raise ValidationError("Cannot record attendance for future dates.")

        # ✅ Validate staff belongs to same school as academic term
        if self.staff.school != self.academic_term.school:
            raise ValidationError("Staff must belong to the same school as academic term.")

    def save(self, *args, **kwargs):
        """Calculate late status and auto-signout."""
        if self.sign_in_time and self.academic_term:
            try:
                school = self.academic_term.school
                if hasattr(school, 'attendance_config') and school.attendance_config:
                    config = school.attendance_config

                    # Check if late
                    school_start = datetime.combine(self.date, config.school_start_time)
                    # Handle timezone-aware datetime
                    sign_in_dt = self.sign_in_time
                    if sign_in_dt.tzinfo:
                        sign_in_dt = sign_in_dt.replace(tzinfo=None)

                    time_diff = (sign_in_dt - school_start).total_seconds() / 60  # minutes
                    self.is_late = time_diff > config.teacher_late_threshold
            except Exception as e:
                logger.warning(f"Error calculating late status: {e}")

        # Auto-signout at school end time if still signed in
        if self.sign_in_time and not self.sign_out_time and self.academic_term:
            try:
                school = self.academic_term.school
                if hasattr(school, 'attendance_config') and school.attendance_config:
                    config = school.attendance_config
                    school_end = datetime.combine(self.date, config.school_end_time)
                    current_time = timezone.now()

                    # Remove timezone for comparison
                    if current_time.tzinfo:
                        current_time = current_time.replace(tzinfo=None)

                    if current_time > school_end:
                        self.sign_out_time = timezone.now()
                        self.auto_signed_out = True
            except Exception as e:
                logger.warning(f"Error auto-signing out: {e}")

        super().save(*args, **kwargs)

    @property
    def work_duration_minutes(self):
        """Calculate work duration in minutes."""
        if self.sign_in_time and self.sign_out_time:
            try:
                return (self.sign_out_time - self.sign_in_time).total_seconds() / 60
            except Exception as e:
                logger.warning(f"Error calculating work duration: {e}")
        return 0

    @property
    def is_currently_signed_in(self):
        """Check if teacher is currently signed in."""
        return self.sign_in_time is not None and self.sign_out_time is None


class AttendanceSummary(models.Model):
    """Monthly/weekly attendance summaries for reporting."""
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='attendance_summaries')
    academic_term = models.ForeignKey('students.AcademicTerm', on_delete=models.CASCADE)

    # Time period
    period_type = models.CharField(max_length=10, choices=(('weekly', 'Weekly'), ('monthly', 'Monthly')))
    start_date = models.DateField()
    end_date = models.DateField()

    # Attendance statistics
    total_days = models.IntegerField(default=0)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    days_late = models.IntegerField(default=0)
    days_excused = models.IntegerField(default=0)

    # Percentage calculations
    attendance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage
    punctuality_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage

    class Meta:
        db_table = 'attendance_summary'
        verbose_name = 'Attendance Summary'
        verbose_name_plural = 'Attendance Summaries'
        unique_together = ['student', 'academic_term', 'period_type', 'start_date']
        indexes = [
            models.Index(fields=['student', 'start_date']),
            models.Index(fields=['academic_term', 'period_type']),
        ]

    def __str__(self):
        return f"{self.student} - {self.period_type} Summary - {self.start_date}"

    def clean(self):
        """Validate summary data."""
        if self.start_date > self.end_date:
            raise ValidationError("End date must be after start date.")

        if self.student.school != self.academic_term.school:
            raise ValidationError("Student must belong to the same school as academic term.")

    def calculate_rates(self):
        """Calculate attendance and punctuality rates."""
        if self.total_days > 0:
            self.attendance_rate = (self.days_present / self.total_days) * 100
            if self.days_present > 0:
                self.punctuality_rate = ((self.days_present - self.days_late) / self.days_present) * 100

    def save(self, *args, **kwargs):
        """Recalculate rates before saving."""
        self.calculate_rates()
        super().save(*args, **kwargs)


class TeacherPerformance(models.Model):
    """Teacher performance tracking based on attendance."""
    staff = models.ForeignKey('users.Staff', on_delete=models.CASCADE, related_name='performance_records')
    academic_term = models.ForeignKey('students.AcademicTerm', on_delete=models.CASCADE)

    # Time period
    period_type = models.CharField(max_length=10, choices=(('weekly', 'Weekly'), ('monthly', 'Monthly')))
    start_date = models.DateField()
    end_date = models.DateField()

    # Performance metrics
    total_work_days = models.IntegerField(default=0)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    days_late = models.IntegerField(default=0)
    average_work_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Performance scores (0-100)
    attendance_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    punctuality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overall_performance = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Additional metrics
    classes_taught = models.IntegerField(default=0)
    extra_duties = models.IntegerField(default=0)

    class Meta:
        db_table = 'attendance_teacher_performance'
        verbose_name = 'Teacher Performance'
        verbose_name_plural = 'Teacher Performance Records'
        unique_together = ['staff', 'academic_term', 'period_type', 'start_date']
        indexes = [
            models.Index(fields=['staff', 'start_date']),
            models.Index(fields=['academic_term', 'period_type']),
        ]

    def __str__(self):
        return f"{self.staff} - {self.period_type} Performance - {self.start_date}"

    def clean(self):
        """Validate performance data."""
        if self.start_date > self.end_date:
            raise ValidationError("End date must be after start date.")

        if self.staff.school != self.academic_term.school:
            raise ValidationError("Staff must belong to the same school as academic term.")

    def calculate_scores(self):
        """Calculate performance scores."""
        if self.total_work_days > 0:
            self.attendance_score = (self.days_present / self.total_work_days) * 100
            if self.days_present > 0:
                self.punctuality_score = ((self.days_present - self.days_late) / self.days_present) * 100

        # Calculate overall performance (weighted average)
        weights = {'attendance': 0.4, 'punctuality': 0.3, 'extra_duties': 0.3}
        extra_duty_score = min(self.extra_duties * 10, 100)  # Cap at 100

        self.overall_performance = (
            self.attendance_score * weights['attendance'] +
            self.punctuality_score * weights['punctuality'] +
            extra_duty_score * weights['extra_duties']
        )

    def save(self, *args, **kwargs):
        """Recalculate scores before saving."""
        self.calculate_scores()
        super().save(*args, **kwargs)
