# attendance/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, date

# ✅ Import shared constants
from shared.constants import StatusChoices

# ✅ Local models
from .models import StudentAttendance, TeacherAttendance, AttendanceConfig


class StudentAttendanceForm(forms.ModelForm):
    """Form for recording student attendance."""
    
    class Meta:
        model = StudentAttendance
        fields = ['status', 'time_in', 'time_out', 'remarks']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'time_in': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'time_out': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Use shared constants for status choices
        self.fields['status'].choices = [
            (StatusChoices.PRESENT, 'Present'),
            (StatusChoices.ABSENT, 'Absent'),
            (StatusChoices.LATE, 'Late'),
            ('excused', 'Excused Absence'),
            ('sick', 'Sick Leave'),
        ]
    
    def clean(self):
        cleaned_data = super().clean()
        time_in = cleaned_data.get('time_in')
        time_out = cleaned_data.get('time_out')
        
        if time_in and time_out and time_in >= time_out:
            raise ValidationError("Time out must be after time in.")
        
        return cleaned_data


class TeacherAttendanceForm(forms.ModelForm):
    """Form for recording teacher attendance."""
    
    class Meta:
        model = TeacherAttendance
        fields = ['status', 'sign_in_time', 'sign_out_time', 'remarks']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'sign_in_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'sign_out_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Use consistent status choices
        self.fields['status'].choices = [
            (StatusChoices.PRESENT, 'Present'),
            (StatusChoices.ABSENT, 'Absent'),
            (StatusChoices.LATE, 'Late'),
            ('half_day', 'Half Day'),
            ('leave', 'On Leave'),
        ]
    
    def clean(self):
        cleaned_data = super().clean()
        sign_in_time = cleaned_data.get('sign_in_time')
        sign_out_time = cleaned_data.get('sign_out_time')
        
        if sign_in_time and sign_out_time and sign_in_time >= sign_out_time:
            raise ValidationError("Sign out time must be after sign in time.")
        
        # Don't allow future sign-in/sign-out times
        now = timezone.now()
        if sign_in_time and sign_in_time > now:
            raise ValidationError("Sign in time cannot be in the future.")
        
        if sign_out_time and sign_out_time > now:
            raise ValidationError("Sign out time cannot be in the future.")
        
        return cleaned_data


class AttendanceConfigForm(forms.ModelForm):
    """Form for configuring attendance settings."""
    
    class Meta:
        model = AttendanceConfig
        fields = [
            'session_type', 'student_marking_enabled', 'auto_mark_absent',
            'late_threshold_minutes', 'early_departure_minutes',
            'teacher_attendance_enabled', 'teacher_signin_required', 'teacher_late_threshold',
            'school_start_time', 'school_end_time', 'break_start_time', 'break_end_time',
            'send_absent_notifications', 'notify_on_late_teachers'
        ]
        widgets = {
            'session_type': forms.Select(attrs={'class': 'form-select'}),
            'school_start_time': forms.TimeInput(attrs={
                'class': 'form-control', 
                'type': 'time',
                'placeholder': '08:00'
            }),
            'school_end_time': forms.TimeInput(attrs={
                'class': 'form-control', 
                'type': 'time',
                'placeholder': '14:00'
            }),
            'break_start_time': forms.TimeInput(attrs={
                'class': 'form-control', 
                'type': 'time',
                'placeholder': '10:00'
            }),
            'break_end_time': forms.TimeInput(attrs={
                'class': 'form-control', 
                'type': 'time',
                'placeholder': '10:30'
            }),
            'late_threshold_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120,
                'placeholder': '30'
            }),
            'early_departure_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120,
                'placeholder': '60'
            }),
            'teacher_late_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 120,
                'placeholder': '15'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        school_start_time = cleaned_data.get('school_start_time')
        school_end_time = cleaned_data.get('school_end_time')
        break_start_time = cleaned_data.get('break_start_time')
        break_end_time = cleaned_data.get('break_end_time')
        
        # Validate school hours
        if school_start_time and school_end_time:
            if school_start_time >= school_end_time:
                raise ValidationError("School end time must be after start time.")
        
        # Validate break times if provided
        if break_start_time and break_end_time:
            if break_start_time >= break_end_time:
                raise ValidationError("Break end time must be after start time.")
            
            # Break must be within school hours
            if school_start_time and school_end_time:
                if (break_start_time < school_start_time or 
                    break_end_time > school_end_time):
                    raise ValidationError("Break times must be within school hours.")
        
        return cleaned_data


class BulkStudentAttendanceForm(forms.Form):
    """Form for bulk student attendance updates."""
    
    def __init__(self, *args, **kwargs):
        students = kwargs.pop('students', [])
        school = kwargs.pop('school', None)
        selected_date = kwargs.pop('selected_date', None)
        super().__init__(*args, **kwargs)
        
        # ✅ Use shared constants for choices
        status_choices = [
            (StatusChoices.PRESENT, 'Present'),
            (StatusChoices.ABSENT, 'Absent'),
            (StatusChoices.LATE, 'Late'),
            ('excused', 'Excused Absence'),
            ('sick', 'Sick Leave'),
        ]
        
        for student in students:
            # Get student's class name safely
            class_name = "No Class"
            if hasattr(student, 'current_class') and student.current_class:
                class_name = student.current_class.name
            elif hasattr(student, 'current_class_id') and student.current_class_id:
                # Try to get class name via shared ClassManager
                try:
                    from shared.models.class_manager import ClassManager
                    class_obj = ClassManager.get_class(
                        student.current_class_id, 
                        school, 
                        raise_exception=False
                    )
                    if class_obj:
                        class_name = class_obj.name
                except:
                    pass
            
            # Get existing attendance status for this date
            initial_status = StatusChoices.PRESENT  # Default to present
            if selected_date:
                try:
                    existing_attendance = StudentAttendance.objects.filter(
                        student=student,
                        date=selected_date
                    ).first()
                    if existing_attendance:
                        initial_status = existing_attendance.status
                except:
                    pass
            
            field_name = f'attendance_{student.id}'
            self.fields[field_name] = forms.ChoiceField(
                choices=status_choices,
                initial=initial_status,
                widget=forms.Select(attrs={
                    'class': 'form-select form-select-sm attendance-select',
                    'data-student-id': student.id,
                    'data-student-name': student.full_name,
                }),
                label=f"{student.full_name}",
                help_text=f"Class: {class_name} | ID: {student.student_id or 'N/A'}"
            )


class ReportFilterForm(forms.Form):
    """Form for filtering attendance reports."""
    
    REPORT_TYPES = [
        ('student', 'Student Attendance'),
        ('teacher', 'Teacher Attendance'),
    ]
    
    PERIOD_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom Date Range'),
    ]
    
    report_type = forms.ChoiceField(
        choices=REPORT_TYPES,
        initial='student',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'hx-get': '',  # For HTMX updates
            'hx-target': '#report-filters',
        })
    )
    
    period = forms.ChoiceField(
        choices=PERIOD_TYPES,
        initial='weekly',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'hx-get': '',  # For HTMX updates
            'hx-target': '#date-fields',
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': timezone.now().date().isoformat(),
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': timezone.now().date().isoformat(),
        })
    )
    
    # Optional filters
    class_filter = forms.IntegerField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Filter by Class"
    )
    
    status_filter = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Statuses'),
            (StatusChoices.PRESENT, 'Present'),
            (StatusChoices.ABSENT, 'Absent'),
            (StatusChoices.LATE, 'Late'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Filter by Status"
    )
    
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set default dates based on period
        period = self.initial.get('period', 'weekly')
        today = timezone.now().date()
        
        if period == 'daily':
            self.initial['date_from'] = today
            self.initial['date_to'] = today
        elif period == 'weekly':
            self.initial['date_from'] = today - timezone.timedelta(days=7)
            self.initial['date_to'] = today
        elif period == 'monthly':
            self.initial['date_from'] = today - timezone.timedelta(days=30)
            self.initial['date_to'] = today
        elif period == 'custom':
            # Custom dates should be provided by user
            pass
        
        # Populate class filter choices if school provided
        if school:
            try:
                from core.models import Class
                classes = Class.objects.filter(school=school, is_active=True)
                class_choices = [(c.id, c.name) for c in classes]
                class_choices.insert(0, ('', 'All Classes'))
                
                self.fields['class_filter'].widget = forms.Select(
                    choices=class_choices,
                    attrs={'class': 'form-select'}
                )
            except:
                # Hide class filter if classes not available
                self.fields.pop('class_filter', None)
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        period = cleaned_data.get('period')
        
        # For custom period, dates are required
        if period == 'custom':
            if not date_from:
                self.add_error('date_from', 'Start date is required for custom period.')
            if not date_to:
                self.add_error('date_to', 'End date is required for custom period.')
        
        # Validate date range
        if date_from and date_to:
            if date_from > date_to:
                raise ValidationError("Start date cannot be after end date.")
            
            # Don't allow future dates
            today = timezone.now().date()
            if date_from > today or date_to > today:
                raise ValidationError("Cannot select dates in the future.")
            
            # Limit to reasonable range (e.g., 1 year max)
            if (date_to - date_from).days > 365:
                raise ValidationError("Date range cannot exceed 365 days.")
        
        return cleaned_data


class QuickAttendanceForm(forms.Form):
    """Quick form for marking attendance with minimal fields."""
    
    STATUS_CHOICES = [
        (StatusChoices.PRESENT, '✓ Present'),
        (StatusChoices.ABSENT, '✗ Absent'),
        (StatusChoices.LATE, '⌚ Late'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial=StatusChoices.PRESENT
    )
    
    remarks = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional remarks...'
        }),
        max_length=100
    )


class AttendanceImportForm(forms.Form):
    """Form for importing attendance data from CSV/Excel."""
    
    IMPORT_TYPES = [
        ('student', 'Student Attendance'),
        ('teacher', 'Teacher Attendance'),
    ]
    
    import_type = forms.ChoiceField(
        choices=IMPORT_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Import Type"
    )
    
    import_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls'
        }),
        label="Select File",
        help_text="Supported formats: CSV, Excel (.xlsx, .xls)"
    )
    
    has_headers = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="File contains headers"
    )
    
    date_column = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Date column name or index'
        }),
        help_text="Leave blank if date is in filename or first column"
    )
    
    def clean_import_file(self):
        import_file = self.cleaned_data.get('import_file')
        if import_file:
            # Validate file extension
            valid_extensions = ['.csv', '.xlsx', '.xls']
            file_name = import_file.name.lower()
            
            if not any(file_name.endswith(ext) for ext in valid_extensions):
                raise ValidationError(
                    f"Invalid file format. Supported formats: {', '.join(valid_extensions)}"
                )
            
            # Validate file size (max 5MB)
            max_size = 5 * 1024 * 1024  # 5MB
            if import_file.size > max_size:
                raise ValidationError("File size cannot exceed 5MB.")
        
        return import_file


class AttendanceNotificationForm(forms.Form):
    """Form for configuring attendance notifications."""
    
    notify_parents = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Notify parents of student absences"
    )
    
    notify_teachers = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Notify administrators of teacher tardiness"
    )
    
    notification_method = forms.ChoiceField(
        choices=[
            ('email', 'Email Only'),
            ('sms', 'SMS Only'),
            ('both', 'Email and SMS'),
        ],
        initial='email',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Notification Method"
    )
    
    send_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time'
        }),
        initial='17:00',  # 5:00 PM
        help_text="Daily time to send notifications"
    )
    
    threshold_days = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=3,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Notify after consecutive days of absence"
    ) 