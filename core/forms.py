# core/forms.py
"""
CLEANED CORE FORMS - Using shared architecture
NO circular imports, PROPER field mapping, VALIDATION
"""
from django import forms
from django.core.exceptions import ValidationError
from django.apps import apps

# SHARED IMPORTS
from shared.constants import (
    CLASS_MODEL_PATH,
    FORM_TO_MODEL
)
from shared.utils import FieldMapper
from shared.models import ClassManager


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'core'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


# ============ CLASS CATEGORY FORM ============

class ClassCategoryForm(forms.ModelForm):
    """Form for creating class categories with shared architecture."""
    
    class Meta:
        model = None  # Will be set in __init__
        fields = ['name', 'section', 'description', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Primary, Secondary, JSS, SSS'
            }),
            'section': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Optional description of this category'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Display order (lower = first)'
            }),
        }
        labels = {
            'display_order': 'Order',
            'section': 'School Section',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('ClassCategory')
        
        # Set default display order
        if not self.instance.pk and not self.initial.get('display_order'):
            if self.school:
                last_category = self._meta.model.objects.filter(
                    school=self.school
                ).order_by('-display_order').first()
                if last_category:
                    self.fields['display_order'].initial = last_category.display_order + 10
                else:
                    self.fields['display_order'].initial = 10
    
    def clean(self):
        """Validate category data."""
        cleaned_data = super().clean()
        
        if self.school:
            name = cleaned_data.get('name')
            
            if name:
                # Check for duplicate names within the same school
                existing_category = self._meta.model.objects.filter(
                    school=self.school,
                    name=name
                )
                
                if self.instance and self.instance.pk:
                    existing_category = existing_category.exclude(pk=self.instance.pk)
                
                if existing_category.exists():
                    raise ValidationError({
                        'name': 'A category with this name already exists in this school.'
                    })
        
        return cleaned_data


# ============ CLASS FORM ============

class ClassForm(forms.ModelForm):
    """Form for creating/editing classes with shared architecture."""
    
    # Use ModelChoiceField for education level
    education_level = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='Education Level',
        help_text='Optional: Link to education level',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = None  # Will be set in __init__
        fields = [
            'name', 'class_type', 'category', 'education_level',
            'academic_year', 'form_master', 'assistant_form_master',
            'max_students', 'room_number'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., SSS 1A, Primary 3B, Drama Club'
            }),
            'class_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'academic_year': forms.Select(attrs={'class': 'form-control'}),
            'form_master': forms.Select(attrs={'class': 'form-control'}),
            'assistant_form_master': forms.Select(attrs={'class': 'form-control'}),
            'max_students': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 100,
                'placeholder': '40'
            }),
            'room_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Room 101, Block A'
            }),
        }
        labels = {
            'form_master': 'Form Master',
            'assistant_form_master': 'Assistant Form Master',
            'max_students': 'Maximum Students',
            'room_number': 'Room Number/Location',
            'class_type': 'Class Type',
        }
        help_texts = {
            'max_students': 'Maximum number of students this class can hold',
            'class_type': 'Academic classes require academic year, others are optional',
            'academic_year': 'Required for academic classes',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('Class')
        
        if self.school:
            # Get models
            ClassCategory = _get_model('ClassCategory')
            AcademicYear = _get_model('AcademicYear')
            Staff = _get_model('Staff', 'users')
            EducationLevel = _get_model('EducationLevel', 'students')
            
            # Filter categories by school
            self.fields['category'].queryset = ClassCategory.objects.filter(
                school=self.school,
                is_active=True
            ).order_by('display_order', 'name')
            
            # Filter academic years by school
            self.fields['academic_year'].queryset = AcademicYear.objects.filter(
                school=self.school,
                is_active=True
            ).order_by('-start_date')
            
            # Filter staff by school
            staff_queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
                is_teaching_staff=True
            ).order_by('first_name', 'last_name')
            
            self.fields['form_master'].queryset = staff_queryset
            self.fields['assistant_form_master'].queryset = staff_queryset
            
            # Filter education levels by school
            self.fields['education_level'].queryset = EducationLevel.objects.filter(
                school=self.school
            ).order_by('level', 'order')
            
            # Make academic_year required for academic classes
            if self.instance and self.instance.class_type == 'academic':
                self.fields['academic_year'].required = True
            else:
                self.fields['academic_year'].required = False
            
            # Add dynamic class type change handler
            self.fields['class_type'].widget.attrs.update({
                'onchange': 'toggleAcademicYearRequirement(this)'
            })
    
    def clean(self):
        """Validate class data with shared field mapping."""
        cleaned_data = super().clean()
        
        # Use FieldMapper to standardize data
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'class')
        
        class_type = cleaned_data.get('class_type')
        academic_year = cleaned_data.get('academic_year')
        form_master = cleaned_data.get('form_master')
        assistant_form_master = cleaned_data.get('assistant_form_master')
        max_students = cleaned_data.get('max_students')
        
        # Validate academic year for academic classes
        if class_type == 'academic' and not academic_year:
            raise ValidationError({
                'academic_year': 'Academic year is required for academic classes.'
            })
        
        # Check if form master and assistant are the same person
        if form_master and assistant_form_master and form_master == assistant_form_master:
            raise ValidationError({
                'assistant_form_master': 'Form master and assistant form master cannot be the same person.'
            })
        
        # Validate max_students
        if max_students and max_students < 1:
            raise ValidationError({
                'max_students': 'Maximum students must be at least 1.'
            })
        
        # Validate name uniqueness within school, academic_year, and class_type
        if self.school:
            name = cleaned_data.get('name')
            class_type = cleaned_data.get('class_type')
            academic_year_id = cleaned_data.get('academic_year')
            
            if name and class_type:
                # Build query for uniqueness check
                query = self._meta.model.objects.filter(
                    school=self.school,
                    name=name,
                    class_type=class_type
                )
                
                # For academic classes, also check academic_year
                if class_type == 'academic' and academic_year_id:
                    query = query.filter(academic_year_id=academic_year_id)
                # For non-academic classes, don't check academic_year
                elif class_type != 'academic':
                    query = query.filter(academic_year__isnull=True)
                
                # Exclude current instance if updating
                if self.instance and self.instance.pk:
                    query = query.exclude(pk=self.instance.pk)
                
                if query.exists():
                    raise ValidationError({
                        'name': f'A {class_type} class with this name already exists.'
                    })
        
        return cleaned_data
    
    def clean_max_students(self):
        """Validate maximum students."""
        max_students = self.cleaned_data.get('max_students')
        
        if max_students is not None and max_students > 200:
            raise ValidationError("Maximum students cannot exceed 200.")
        
        return max_students


# ============ CLASS SUBJECT FORM ============

class ClassSubjectForm(forms.ModelForm):
    """Form for adding subjects to classes with shared architecture."""
    
    class Meta:
        model = None  # Will be set in __init__
        fields = ['subject', 'teacher', 'is_compulsory', 'periods_per_week', 'elective_group', 'display_order']
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-control'}),
            'is_compulsory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'periods_per_week': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 20,
                'placeholder': '5'
            }),
            'elective_group': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Science Elective, Arts Elective'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': '0'
            }),
        }
        labels = {
            'is_compulsory': 'Compulsory Subject',
            'periods_per_week': 'Periods per Week',
            'elective_group': 'Elective Group',
            'display_order': 'Display Order',
        }
        help_texts = {
            'periods_per_week': 'Number of teaching periods per week (1-20)',
            'elective_group': 'Group name for elective subjects (optional)',
            'display_order': 'Order in which subject appears (lower = first)',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('ClassSubject')
        
        if self.school:
            # Get models
            Subject = _get_model('Subject')
            Staff = _get_model('Staff', 'users')
            
            # Filter subjects by school
            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school,
                is_active=True
            ).order_by('category', 'name')
            
            # Filter teachers by school
            self.fields['teacher'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
                is_teaching_staff=True
            ).order_by('first_name', 'last_name')
            
            # Set default periods per week
            if not self.instance.pk:
                self.fields['periods_per_week'].initial = 5
            
            # Show/hide elective group based on compulsory status
            self.fields['elective_group'].widget.attrs.update({
                'style': 'display: none;',
                'class': 'form-control elective-field'
            })
            self.fields['is_compulsory'].widget.attrs.update({
                'onchange': 'toggleElectiveGroup(this)'
            })
    
    def clean(self):
        """Validate class subject assignment."""
        cleaned_data = super().clean()
        
        subject = cleaned_data.get('subject')
        teacher = cleaned_data.get('teacher')
        periods_per_week = cleaned_data.get('periods_per_week')
        is_compulsory = cleaned_data.get('is_compulsory', True)
        elective_group = cleaned_data.get('elective_group')
        
        # Validate periods per week
        if periods_per_week:
            if periods_per_week < 1 or periods_per_week > 20:
                raise ValidationError({
                    'periods_per_week': 'Periods per week must be between 1 and 20.'
                })
        
        # Validate elective group for non-compulsory subjects
        if not is_compulsory and not elective_group:
            raise ValidationError({
                'elective_group': 'Elective group is required for non-compulsory subjects.'
            })
        
        # Validate teacher belongs to same school as subject
        if teacher and subject and teacher.school != subject.school:
            raise ValidationError({
                'teacher': 'Teacher must be from the same school as the subject.'
            })
        
        return cleaned_data
    
    def clean_periods_per_week(self):
        """Validate periods per week."""
        periods = self.cleaned_data.get('periods_per_week')
        
        if periods is not None and periods < 0:
            raise ValidationError("Periods per week cannot be negative.")
        
        return periods


# ============ SUBJECT FORM ============

class SubjectForm(forms.ModelForm):
    """Form for creating/editing subjects with shared architecture."""
    
    class Meta:
        model = None  # Will be set in __init__
        fields = [
            'name', 'code', 'category', 'difficulty_level',
            'description', 'max_score', 'pass_score', 'display_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Mathematics, English Language, Biology'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., MATH, ENG, BIO'
            }),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'difficulty_level': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the subject, learning objectives...'
            }),
            'max_score': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 1000,
                'placeholder': '100'
            }),
            'pass_score': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 1000,
                'placeholder': '40'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': '0'
            }),
        }
        labels = {
            'max_score': 'Maximum Score',
            'pass_score': 'Passing Score',
            'display_order': 'Display Order',
            'difficulty_level': 'Difficulty Level',
        }
        help_texts = {
            'code': 'Unique subject code (auto-generated if blank)',
            'max_score': 'Maximum possible score for this subject',
            'pass_score': 'Minimum score required to pass',
            'display_order': 'Order in which subject appears (lower = first)',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('Subject')
        
        # Set default values
        if not self.instance.pk:
            self.fields['max_score'].initial = 100
            self.fields['pass_score'].initial = 40
            self.fields['display_order'].initial = 0
            self.fields['difficulty_level'].initial = 'basic'
        
        # Add code generation hint
        self.fields['code'].help_text = "Leave blank to auto-generate from name"
    
    def clean(self):
        """Validate subject data."""
        cleaned_data = super().clean()
        
        if self.school:
            name = cleaned_data.get('name')
            code = cleaned_data.get('code')
            
            # Check name uniqueness within school
            if name:
                existing_subject = self._meta.model.objects.filter(
                    school=self.school,
                    name=name
                )
                
                if self.instance and self.instance.pk:
                    existing_subject = existing_subject.exclude(pk=self.instance.pk)
                
                if existing_subject.exists():
                    raise ValidationError({
                        'name': 'A subject with this name already exists in this school.'
                    })
            
            # Check code uniqueness within school
            if code:
                existing_subject = self._meta.model.objects.filter(
                    school=self.school,
                    code=code
                )
                
                if self.instance and self.instance.pk:
                    existing_subject = existing_subject.exclude(pk=self.instance.pk)
                
                if existing_subject.exists():
                    raise ValidationError({
                        'code': 'A subject with this code already exists in this school.'
                    })
                        
            # Auto-generate code if not provided
            if not code and name:
                # Generate code from name (first 4 letters, uppercase)
                generated_code = name[:4].upper().replace(' ', '')
                
                # Ensure uniqueness
                counter = 1
                base_code = generated_code
                while self._meta.model.objects.filter(school=self.school, code=generated_code).exists():
                    generated_code = f"{base_code}{counter}"
                    counter += 1
                
                cleaned_data['code'] = generated_code
        
        # Validate scores
        max_score = cleaned_data.get('max_score')
        pass_score = cleaned_data.get('pass_score')
        
        if max_score is not None and pass_score is not None:
            if max_score <= 0:
                raise ValidationError({
                    'max_score': 'Maximum score must be greater than 0.'
                })
            
            if pass_score < 0:
                raise ValidationError({
                    'pass_score': 'Passing score cannot be negative.'
                })
            
            if pass_score > max_score:
                raise ValidationError({
                    'pass_score': f'Passing score cannot exceed maximum score ({max_score}).'
                })
        
        return cleaned_data
    
    def clean_code(self):
        """Validate subject code."""
        code = self.cleaned_data.get('code')
        
        if code:
            # Ensure code is alphanumeric and uppercase
            code = code.strip().upper()
            
            if not code.replace('_', '').isalnum():
                raise ValidationError('Subject code can only contain letters, numbers, and underscores.')
            
            if len(code) > 20:
                raise ValidationError('Subject code cannot exceed 20 characters.')
        
        return code


# ============ CLASS MONITOR FORM ============

class ClassMonitorForm(forms.ModelForm):
    """Form for assigning class monitors with shared architecture."""
    
    class Meta:
        model = None  # Will be set in __init__
        fields = ['student', 'role', 'position', 'responsibilities', 'start_date', 'end_date']
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Head Boy, Games Captain'
            }),
            'responsibilities': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'List key responsibilities...'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }
        labels = {
            'start_date': 'Start Date',
            'end_date': 'End Date (optional)',
        }
        help_texts = {
            'role': 'Select the monitor role',
            'position': 'Specific position title',
            'responsibilities': 'Key duties and responsibilities',
        }
    
    def __init__(self, *args, **kwargs):
        self.class_instance = kwargs.pop('class_instance', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('ClassMonitor')
        
        if self.class_instance:
            # Filter students to those in this class
            Student = _get_model('Student', 'students')
            self.fields['student'].queryset = Student.objects.filter(
                current_class=self.class_instance,
                is_active=True
            ).order_by('first_name', 'last_name')
            
            # Set default start date
            if not self.instance.pk:
                self.fields['start_date'].initial = timezone.now().date()
    
    def clean(self):
        """Validate monitor assignment."""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        student = cleaned_data.get('student')
        role = cleaned_data.get('role')
        
        # Validate dates
        if start_date and end_date and end_date < start_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        # Check if student is already a monitor in this class
        if student and role and self.class_instance:
            existing_monitor = self._meta.model.objects.filter(
                class_instance=self.class_instance,
                student=student,
                role=role,
                is_active=True
            )
            
            if self.instance and self.instance.pk:
                existing_monitor = existing_monitor.exclude(pk=self.instance.pk)
            
            if existing_monitor.exists():
                raise ValidationError({
                    'student': f'{student.full_name} is already assigned as {role} in this class.'
                })
        
        return cleaned_data


# ============ ACADEMIC YEAR FORM ============

class AcademicYearForm(forms.ModelForm):
    """Form for creating/editing academic years."""
    
    class Meta:
        model = None  # Will be set in __init__
        fields = ['name', 'start_date', 'end_date', 'is_current']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2024/2025'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'is_current': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_current': 'Set as Current Academic Year',
        }
        help_texts = {
            'name': 'Format: YYYY/YYYY (e.g., 2024/2025)',
            'is_current': 'Only one academic year can be current at a time',
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set the model class dynamically
        self._meta.model = _get_model('AcademicYear')
    
    def clean(self):
        """Validate academic year data."""
        cleaned_data = super().clean()
        
        name = cleaned_data.get('name')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        # Validate name format
        if name:
            import re
            if not re.match(r'^\d{4}/\d{4}$', name):
                raise ValidationError({
                    'name': 'Academic year must be in format: YYYY/YYYY'
                })
            
            # Extract years
            try:
                start_year, end_year = map(int, name.split('/'))
                if end_year != start_year + 1:
                    raise ValidationError({
                        'name': 'End year must be one year after start year (e.g., 2024/2025)'
                    })
            except ValueError:
                raise ValidationError({
                    'name': 'Invalid year format'
                })
        
        # Validate dates
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            
            # Check if dates match the academic year name
            if name:
                try:
                    start_year, end_year = map(int, name.split('/'))
                    if start_date.year != start_year or end_date.year != end_year:
                        raise ValidationError({
                            'name': 'Academic year dates must match the year in the name.'
                        })
                except ValueError:
                    pass
        
        # Check name uniqueness within school
        if self.school and name:
            existing_year = self._meta.model.objects.filter(
                school=self.school,
                name=name
            )
            
            if self.instance and self.instance.pk:
                existing_year = existing_year.exclude(pk=self.instance.pk)
            
            if existing_year.exists():
                raise ValidationError({
                    'name': 'An academic year with this name already exists in this school.'
                })
        
        return cleaned_data 
