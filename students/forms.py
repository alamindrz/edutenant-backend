# students/forms.py
"""
CLEANED STUDENT FORMS - Using shared architecture
NO ClassGroup references, PROPER field mapping, VALIDATION
"""
from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError

# SHARED IMPORTS
from shared.constants import (
    PARENT_PHONE_FIELD,
    PARENT_EMAIL_FIELD,
    STUDENT_CLASS_FIELD,
    CLASS_MODEL_PATH,
    StatusChoices,
    FORM_TO_MODEL
)
from shared.utils import FieldMapper
from shared.models import ClassManager

# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'students'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


# ============ PARENT FORMS ============

class ParentCreationForm(forms.ModelForm):
    """Form for creating parents with shared architecture."""
    create_user_account = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Create a user account for this parent",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # Use shared constant for phone field
    phone_number = forms.CharField(
        label='Phone Number',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., +2348012345678'
        })
    )
    
    class Meta:
        model = _get_model('Parent')
        fields = [
            'first_name', 'last_name', PARENT_EMAIL_FIELD, PARENT_PHONE_FIELD,
            'address', 'relationship', 'is_staff_child', 'staff_member'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            PARENT_EMAIL_FIELD: forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Full address'
            }),
            'relationship': forms.Select(attrs={'class': 'form-control'}),
            'is_staff_child': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'staff_member': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            PARENT_EMAIL_FIELD: 'Email Address',
            'is_staff_child': 'Is this a staff member\'s child?',
            'staff_member': 'Staff Member (if staff child)',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter staff members to current school
            Staff = _get_model('Staff', 'users')
            self.fields['staff_member'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True
            ).order_by('first_name', 'last_name')
            
            # Make staff_member field optional by default
            self.fields['staff_member'].required = False
            
            # Add help text
            self.fields['staff_member'].help_text = "Required only if this is a staff child"
            
            # Hide staff fields initially
            self.fields['is_staff_child'].widget.attrs.update({
                'onchange': 'toggleStaffFields(this)'
            })
            self.fields['staff_member'].widget.attrs.update({
                'style': 'display: none;',
                'class': 'form-control staff-field'
            })
    
    def clean(self):
        """Validate form data with shared field mapping."""
        cleaned_data = super().clean()
        
        # Use FieldMapper to standardize data
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'parent')
        
        # Validate staff child consistency
        is_staff_child = cleaned_data.get('is_staff_child', False)
        staff_member = cleaned_data.get('staff_member')
        
        if is_staff_child and not staff_member:
            raise ValidationError({
                'staff_member': 'Staff member must be specified for staff children.'
            })
        
        if staff_member and not is_staff_child:
            raise ValidationError({
                'is_staff_child': 'Must be marked as staff child if staff member is specified.'
            })
        
        # Validate email uniqueness within school
        email = cleaned_data.get(PARENT_EMAIL_FIELD)
        if email and self.school:
            Parent = _get_model('Parent')
            existing_parent = Parent.objects.filter(
                school=self.school,
                email=email
            )
            
            if self.instance and self.instance.pk:
                existing_parent = existing_parent.exclude(pk=self.instance.pk)
            
            if existing_parent.exists():
                raise ValidationError({
                    PARENT_EMAIL_FIELD: 'A parent with this email already exists in this school.'
                })
        
        # Validate phone number
        phone = cleaned_data.get(PARENT_PHONE_FIELD)
        if phone:
            # Standardize phone number using FieldMapper
            cleaned_data[PARENT_PHONE_FIELD] = FieldMapper.standardize_phone_number(phone)
        
        return cleaned_data
    
    def clean_phone_number(self):
        """Custom phone validation for Nigeria."""
        phone = self.cleaned_data.get(PARENT_PHONE_FIELD)
        if phone:
            # Remove all non-digit characters for validation
            digits = ''.join(filter(str.isdigit, str(phone)))
            
            # Nigerian phone validation
            if len(digits) < 10:
                raise ValidationError("Enter a valid Nigerian phone number.")
            
            # Ensure it starts with valid prefix
            if not (digits.startswith('0') or digits.startswith('234')):
                raise ValidationError("Phone number must start with 0 or 234.")
        
        return phone


# ============ STUDENT FORMS ============

class StudentCreationForm(forms.ModelForm):
    """Form for creating students with core.Class integration."""
    
    # Use shared constant for class field
    current_class = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='Class',
        help_text='Select the student\'s current class',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = _get_model('Student')
        fields = [
            'first_name', 'last_name', 'gender', 'date_of_birth',
            'parent', 'education_level', 'current_class',  # ✅ Use current_class, not class_group
            'admission_status', 'is_staff_child',
            'medical_conditions', 'allergies', 'emergency_contact',
            'nationality', 'state_of_origin', 'religion'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'parent': forms.Select(attrs={'class': 'form-control'}),
            'education_level': forms.Select(attrs={'class': 'form-control'}),
            'admission_status': forms.Select(attrs={'class': 'form-control'}),
            'is_staff_child': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'medical_conditions': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Any known medical conditions'
            }),
            'allergies': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Any known allergies'
            }),
            'emergency_contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+2348012345678'
            }),
            'nationality': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nationality'
            }),
            'state_of_origin': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State of Origin'
            }),
            'religion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Religion'
            }),
        }
        labels = {
            'current_class': 'Class Assignment',
            'is_staff_child': 'Is this a staff member\'s child?',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter parents to current school
            Parent = _get_model('Parent')
            self.fields['parent'].queryset = Parent.objects.filter(
                school=self.school
            ).order_by('first_name', 'last_name')
            
            # Filter education levels to current school
            EducationLevel = _get_model('EducationLevel')
            self.fields['education_level'].queryset = EducationLevel.objects.filter(
                school=self.school
            ).order_by('level', 'order')
            
            # Get class choices using ClassManager
            class_choices = ClassManager.get_class_choices(self.school)
            self.fields['current_class'].queryset = ClassManager.get_classes_queryset(self.school)
            
            # Add dynamic class loading for education level
            self.fields['education_level'].widget.attrs.update({
                'hx-get': f'/students/ajax/classes-for-level/',
                'hx-target': '#id_current_class',
                'hx-trigger': 'change',
                'hx-swap': 'innerHTML'
            })
            
            # Hide staff child fields initially
            self.fields['is_staff_child'].widget.attrs.update({
                'onchange': 'toggleStaffChildFields(this)'
            })
        
        # Set default admission status
        if not self.instance.pk:
            self.fields['admission_status'].initial = StatusChoices.PENDING
        
        # Set default nationality
        if not self.instance.pk or not self.instance.nationality:
            self.fields['nationality'].initial = 'Nigerian'
    
    def clean(self):
        """Validate student data with shared field mapping."""
        cleaned_data = super().clean()
        
        # Use FieldMapper to standardize data
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'student')
        
        # Validate staff child consistency
        is_staff_child = cleaned_data.get('is_staff_child', False)
        parent = cleaned_data.get('parent')
        
        if is_staff_child and parent and not parent.is_staff_child:
            raise ValidationError({
                'is_staff_child': 'Parent must also be marked as staff child.'
            })
        
        # Validate dates
        date_of_birth = cleaned_data.get('date_of_birth')
        if date_of_birth:
            from django.utils import timezone
            if date_of_birth > timezone.now().date():
                raise ValidationError({
                    'date_of_birth': 'Date of birth cannot be in the future.'
                })
        
        # Validate class capacity if class is selected
        current_class_id = cleaned_data.get('current_class_id')
        if current_class_id and self.school:
            is_available, message, class_instance = ClassManager.validate_class_availability(
                current_class_id, self.school, is_staff_child
            )
            if not is_available:
                raise ValidationError({
                    'current_class': message
                })
        
        return cleaned_data
    
    def clean_admission_number(self):
        """Validate admission number uniqueness."""
        admission_number = self.cleaned_data.get('admission_number')
        
        if admission_number and self.school:
            Student = _get_model('Student')
            existing_student = Student.objects.filter(
                school=self.school,
                admission_number=admission_number
            )
            
            if self.instance and self.instance.pk:
                existing_student = existing_student.exclude(pk=self.instance.pk)
            
            if existing_student.exists():
                raise ValidationError('A student with this admission number already exists.')
        
        return admission_number


# ============ EDUCATION LEVEL FORMS ============

class EducationLevelForm(forms.ModelForm):
    """Form for creating education levels."""
    
    class Meta:
        model = _get_model('EducationLevel')
        fields = ['level', 'name', 'order', 'description']
        widgets = {
            'level': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Primary 1, JSS 2'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Display order'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Optional description'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        """Validate education level uniqueness."""
        cleaned_data = super().clean()
        
        if self.school:
            level = cleaned_data.get('level')
            name = cleaned_data.get('name')
            
            if level and name:
                EducationLevel = _get_model('EducationLevel')
                existing_level = EducationLevel.objects.filter(
                    school=self.school,
                    level=level,
                    name=name
                )
                
                if self.instance and self.instance.pk:
                    existing_level = existing_level.exclude(pk=self.instance.pk)
                
                if existing_level.exists():
                    raise ValidationError(
                        'An education level with this name already exists for this school level.'
                    )
        
        return cleaned_data


# ============ ACADEMIC TERM FORMS ============

class AcademicTermForm(forms.ModelForm):
    """Form for creating academic terms."""
    
    class Meta:
        model = _get_model('AcademicTerm')
        fields = [
            'name', 'term', 'academic_year', 'start_date', 'end_date',
            'planned_weeks', 'mid_term_break_start', 'mid_term_break_end',
            'status'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., First Term 2024'
            }),
            'term': forms.Select(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '2024/2025'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'planned_weeks': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '12',
                'max': '20',
                'placeholder': '12'
            }),
            'mid_term_break_start': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'mid_term_break_end': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'planned_weeks': 'Planned Duration (Weeks)',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set default academic year to current
        from datetime import datetime
        current_year = datetime.now().year
        if not self.instance.pk:
            self.fields['academic_year'].initial = f"{current_year}/{current_year + 1}"
            self.fields['status'].initial = 'upcoming'
    
    def clean_academic_year(self):
        """Validate academic year format."""
        import re
        academic_year = self.cleaned_data.get('academic_year')
        
        if not re.match(r'^\d{4}/\d{4}$', academic_year):
            raise ValidationError("Academic year must be in format: YYYY/YYYY")
        
        # Extract years
        start_year, end_year = map(int, academic_year.split('/'))
        
        if end_year != start_year + 1:
            raise ValidationError("End year must be one year after start year (e.g., 2024/2025)")
        
        return academic_year
    
    def clean(self):
        """Validate term dates and logic."""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        mid_term_start = cleaned_data.get('mid_term_break_start')
        mid_term_end = cleaned_data.get('mid_term_break_end')
        
        # Validate start and end dates
        if start_date and end_date and start_date >= end_date:
            raise ValidationError("End date must be after start date.")
        
        # Validate mid-term break dates
        if mid_term_start and mid_term_end:
            if mid_term_start >= mid_term_end:
                raise ValidationError("Mid-term break end must be after start.")
            
            if start_date and end_date:
                if mid_term_start < start_date or mid_term_end > end_date:
                    raise ValidationError("Mid-term break must be within term dates.")
        
        # Validate academic year uniqueness within school
        academic_year = cleaned_data.get('academic_year')
        term = cleaned_data.get('term')
        
        if academic_year and term and self.school:
            AcademicTerm = _get_model('AcademicTerm')
            existing_term = AcademicTerm.objects.filter(
                school=self.school,
                academic_year=academic_year,
                term=term
            )
            
            if self.instance and self.instance.pk:
                existing_term = existing_term.exclude(pk=self.instance.pk)
            
            if existing_term.exists():
                raise ValidationError(
                    f'A {term.replace("_", " ").title()} term already exists for {academic_year}.'
                )
        
        return cleaned_data


# ============ ENROLLMENT FORMS ============

class EnrollmentForm(forms.ModelForm):
    """Form for enrolling students in academic terms."""
    
    class Meta:
        model = _get_model('Enrollment')
        fields = ['academic_term', 'enrollment_type', 'notes']
        widgets = {
            'academic_term': forms.Select(attrs={'class': 'form-control'}),
            'enrollment_type': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Optional notes about this enrollment'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter academic terms to current school
            AcademicTerm = _get_model('AcademicTerm')
            self.fields['academic_term'].queryset = AcademicTerm.objects.filter(
                school=self.school
            ).order_by('-academic_year', 'start_date')
            
            # Set default enrollment type
            if not self.instance.pk:
                self.fields['enrollment_type'].initial = 'continuing'
    
    def clean(self):
        """Validate enrollment data."""
        cleaned_data = super().clean()
        
        if self.student and self.school:
            academic_term = cleaned_data.get('academic_term')
            
            # Check if student is already enrolled in this term
            if academic_term:
                Enrollment = _get_model('Enrollment')
                existing_enrollment = Enrollment.objects.filter(
                    student=self.student,
                    academic_term=academic_term
                )
                
                if self.instance and self.instance.pk:
                    existing_enrollment = existing_enrollment.exclude(pk=self.instance.pk)
                
                if existing_enrollment.exists():
                    raise ValidationError({
                        'academic_term': f'Student is already enrolled in {academic_term.name}.'
                    })
                
                # Validate that term belongs to same school as student
                if academic_term.school != self.school:
                    raise ValidationError({
                        'academic_term': 'Academic term must be from the same school.'
                    })
        
        return cleaned_data


# ============ ATTENDANCE FORMS ============

class AttendanceForm(forms.ModelForm):
    """Form for recording student attendance."""
    
    class Meta:
        model = _get_model('Attendance')
        fields = ['academic_term', 'date', 'status', 'time_in', 'time_out', 'remarks']
        widgets = {
            'academic_term': forms.Select(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'time_in': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }),
            'time_out': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }),
            'remarks': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Optional remarks'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter academic terms to current school
            AcademicTerm = _get_model('AcademicTerm')
            self.fields['academic_term'].queryset = AcademicTerm.objects.filter(
                school=self.school
            ).order_by('-academic_year', 'start_date')
            
            # Set default status
            if not self.instance.pk:
                self.fields['status'].initial = 'present'
                self.fields['date'].initial = timezone.now().date()
    
    def clean(self):
        """Validate attendance data."""
        cleaned_data = super().clean()
        
        date = cleaned_data.get('date')
        time_in = cleaned_data.get('time_in')
        time_out = cleaned_data.get('time_out')
        academic_term = cleaned_data.get('academic_term')
        
        # Validate time consistency
        if time_out and time_in and time_out < time_in:
            raise ValidationError({
                'time_out': 'Time out cannot be before time in.'
            })
        
        # Validate date is within academic term
        if date and academic_term:
            term_start = academic_term.start_date
            term_end = academic_term.actual_end_date or academic_term.end_date
            
            if date < term_start:
                raise ValidationError({
                    'date': f'Date cannot be before term start ({term_start}).'
                })
            
            if date > term_end:
                raise ValidationError({
                    'date': f'Date cannot be after term end ({term_end}).'
                })
        
        # Check for duplicate attendance record
        if self.student and date:
            Attendance = _get_model('Attendance')
            existing_attendance = Attendance.objects.filter(
                student=self.student,
                date=date
            )
            
            if self.instance and self.instance.pk:
                existing_attendance = existing_attendance.exclude(pk=self.instance.pk)
            
            if existing_attendance.exists():
                raise ValidationError({
                    'date': 'Attendance already recorded for this student on this date.'
                })
        
        return cleaned_data


# ============ SCORE FORMS ============

class ScoreForm(forms.ModelForm):
    """Form for recording student scores."""
    
    class Meta:
        model = _get_model('Score')
        fields = [
            'subject', 'score', 'maximum_score', 'assessment_type',
            'assessment_name', 'assessment_date', 'remarks'
        ]
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-control'}),
            'score': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'maximum_score': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'assessment_type': forms.Select(attrs={'class': 'form-control'}),
            'assessment_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., First Term Exam'
            }),
            'assessment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'remarks': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Optional remarks'
            }),
        }
        labels = {
            'maximum_score': 'Maximum Possible Score',
            'assessment_name': 'Assessment Name',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.enrollment = kwargs.pop('enrollment', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter subjects to current school
            Subject = _get_model('Subject', 'core')
            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school
            ).order_by('name')
            
            # Set default values
            if not self.instance.pk:
                self.fields['maximum_score'].initial = 100
                self.fields['assessment_date'].initial = timezone.now().date()
    
    def clean(self):
        """Validate score data."""
        cleaned_data = super().clean()
        
        score = cleaned_data.get('score')
        maximum_score = cleaned_data.get('maximum_score')
        
        # Validate score values
        if score is not None and maximum_score is not None:
            if score < 0:
                raise ValidationError({
                    'score': 'Score cannot be negative.'
                })
            
            if maximum_score <= 0:
                raise ValidationError({
                    'maximum_score': 'Maximum score must be greater than 0.'
                })
            
            if score > maximum_score:
                raise ValidationError({
                    'score': f'Score ({score}) cannot exceed maximum score ({maximum_score}).'
                })
        
        return cleaned_data