# core/forms.py
from django import forms
from .models import Class, ClassCategory, ClassSubject, Subject

class ClassCategoryForm(forms.ModelForm):
    """Form for creating class categories."""
    class Meta:
        model = ClassCategory
        fields = ['name', 'section', 'description', 'display_order']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})




class ClassForm(forms.ModelForm):
    class Meta:
        model = Class
        fields = [
            'category', 'name', 'code', 'form_master', 'assistant_form_master',
            'max_students', 'room_number', 'academic_session', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., SSS 1A, Primary 3B',
                'class': 'form-control'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'Auto-generated if left blank',
                'class': 'form-control'
            }),
            'max_students': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 100
            }),
            'room_number': forms.TextInput(attrs={
                'placeholder': 'e.g., Room 101, Block A',
                'class': 'form-control'
            }),
            'academic_session': forms.TextInput(attrs={
                'placeholder': 'e.g., 2024/2025',
                'class': 'form-control'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'form_master': forms.Select(attrs={'class': 'form-select'}),
            'assistant_form_master': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'form_master': 'Form Master',
            'assistant_form_master': 'Assistant Form Master',
            'max_students': 'Maximum Students',
            'room_number': 'Room Number/Location',
            'academic_session': 'Academic Session',
            'is_active': 'Active Status'
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            # Filter categories by school
            self.fields['category'].queryset = ClassCategory.objects.filter(school=self.school)
            
            # Filter staff by school
            from users.models import Staff
            self.fields['form_master'].queryset = Staff.objects.filter(school=self.school, is_active=True)
            self.fields['assistant_form_master'].queryset = Staff.objects.filter(school=self.school, is_active=True)
        
        # Make code field not required since it's auto-generated
        self.fields['code'].required = False
        
        # Add help text
        self.fields['code'].help_text = "Leave blank to auto-generate"
        self.fields['max_students'].help_text = "Maximum number of students this class can hold"
        self.fields['is_active'].help_text = "Inactive classes won't be available for new student assignments"
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            # Check if code is unique (excluding current instance)
            queryset = Class.objects.filter(code=code)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise forms.ValidationError("A class with this code already exists.")
        return code
    
    def clean_max_students(self):
        max_students = self.cleaned_data.get('max_students')
        if max_students and max_students < 1:
            raise forms.ValidationError("Maximum students must be at least 1.")
        return max_students
    
    def clean(self):
        cleaned_data = super().clean()
        form_master = cleaned_data.get('form_master')
        assistant_form_master = cleaned_data.get('assistant_form_master')
        
        # Check if form master and assistant are the same person
        if form_master and assistant_form_master and form_master == assistant_form_master:
            raise forms.ValidationError("Form master and assistant form master cannot be the same person.")
        
        return cleaned_data




class ClassSubjectForm(forms.ModelForm):
    """Form for adding subjects to classes."""
    class Meta:
        model = ClassSubject
        fields = ['subject', 'teacher', 'is_compulsory', 'display_order']
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets to current school
        if self.school:
            self.fields['subject'].queryset = Subject.objects.filter(school=self.school, is_active=True)
            self.fields['teacher'].queryset = self.school.attendance_staff.filter(is_active=True)
        
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
            
            
class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'description', 'category', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Mathematics, Science, English',
                'class': 'form-control'
            }),
            'code': forms.TextInput(attrs={
                'placeholder': 'e.g., MATH, SCI, ENG',
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Describe the subject, learning objectives...',
                'class': 'form-control',
                'rows': 4
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Make code field not required since it's auto-generated
        self.fields['code'].required = False
        self.fields['code'].help_text = "Leave blank to auto-generate"
    
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            # Check if code is unique (excluding current instance)
            queryset = Subject.objects.filter(code=code, school=self.school)
            
            # Exclude current instance if we're updating
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise forms.ValidationError("A subject with this code already exists.")
        
        return code
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Check if name is unique for this school (excluding current instance)
            queryset = Subject.objects.filter(name=name, school=self.school)
            
            # Exclude current instance if we're updating
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise forms.ValidationError("A subject with this name already exists.")
        
        return name