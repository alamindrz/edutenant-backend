# attendance/forms.py
from django import forms
from django.core.exceptions import ValidationError
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
    
    def clean(self):
        cleaned_data = super().clean()
        sign_in_time = cleaned_data.get('sign_in_time')
        sign_out_time = cleaned_data.get('sign_out_time')
        
        if sign_in_time and sign_out_time and sign_in_time >= sign_out_time:
            raise ValidationError("Sign out time must be after sign in time.")
        
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
            'school_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'school_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'break_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'break_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'late_threshold_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'early_departure_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'teacher_late_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class BulkStudentAttendanceForm(forms.Form):
    """Form for bulk student attendance updates."""
    
    def __init__(self, *args, **kwargs):
        students = kwargs.pop('students', [])
        super().__init__(*args, **kwargs)
        
        for student in students:
            self.fields[f'student_{student.id}'] = forms.ChoiceField(
                choices=[
                    ('present', 'Present'),
                    ('absent', 'Absent'),
                    ('late', 'Late'),
                    ('excused', 'Excused'),
                    ('sick', 'Sick Leave'),
                ],
                initial='present',
                widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
                label=f"{student.full_name} ({student.class_group.name if student.class_group else 'No Class'})"
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
    ]
    
    report_type = forms.ChoiceField(
        choices=REPORT_TYPES,
        initial='student',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    period = forms.ChoiceField(
        choices=PERIOD_TYPES,
        initial='weekly',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Date from cannot be after date to.")
        
        return cleaned_data