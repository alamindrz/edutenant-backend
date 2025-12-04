# students/forms.py
from django import forms
from .models import Student, Parent, ClassGroup, EducationLevel, AcademicTerm





class AcademicTermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = [
            'name', 'term', 'academic_year', 'start_date', 'end_date',
            'planned_weeks', 'mid_term_break_start', 'mid_term_break_end'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., First Term 2024'}),
            'term': forms.Select(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '2024/2025'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'planned_weeks': forms.NumberInput(attrs={'class': 'form-control', 'min': '12', 'max': '20'}),
            'mid_term_break_start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'mid_term_break_end': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
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
    
    def clean_academic_year(self):
        """Validate academic year format."""
        academic_year = self.cleaned_data['academic_year']
        import re
        if not re.match(r'^\d{4}/\d{4}$', academic_year):
            raise forms.ValidationError("Academic year must be in format: YYYY/YYYY")
        return academic_year
            
            
class ParentCreationForm(forms.ModelForm):
    """Form for creating parents."""
    create_user_account = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Create a user account for this parent"
    )
    
    class Meta:
        model = Parent
        fields = [
            'first_name', 'last_name', 'email', 'phone_number', 
            'address', 'relationship'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        for field_name, field in self.fields.items():
            if isinstance(field, (forms.CharField, forms.EmailField)):
                field.widget.attrs.update({'class': 'form-control'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and Parent.objects.filter(email=email, school=self.school).exists():
            raise forms.ValidationError("A parent with this email already exists.")
        return email

class StudentCreationForm(forms.ModelForm):
    """Form for creating students."""
    class Meta:
        model = Student
        fields = [
            'first_name', 'last_name', 'gender', 'date_of_birth',
            'parent', 'education_level', 'class_group',
            'medical_conditions', 'allergies', 'emergency_contact'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'medical_conditions': forms.Textarea(attrs={'rows': 2}),
            'allergies': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets to current school
        if self.school:
            self.fields['parent'].queryset = Parent.objects.filter(school=self.school)
            self.fields['education_level'].queryset = EducationLevel.objects.filter(school=self.school)
            self.fields['class_group'].queryset = ClassGroup.objects.filter(school=self.school)
        
        for field_name, field in self.fields.items():
            if isinstance(field, (forms.CharField, forms.ChoiceField)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field, forms.ModelChoiceField):
                field.widget.attrs.update({'class': 'form-control'})

class ClassGroupForm(forms.ModelForm):
    """Form for creating class groups."""
    class Meta:
        model = ClassGroup
        fields = [
            'name', 'education_level', 'class_teacher', 'teachers', 'capacity'
        ]
        widgets = {
            'teachers': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Filter querysets to current school
        if self.school:
            self.fields['education_level'].queryset = EducationLevel.objects.filter(school=self.school)
            self.fields['class_teacher'].queryset = self.school.profile_set.filter(
                role__category='academic'
            )
            self.fields['teachers'].queryset = self.school.profile_set.filter(
                role__category='academic'
            )
        
        for field_name, field in self.fields.items():
            if isinstance(field, (forms.CharField, forms.ChoiceField, forms.ModelChoiceField)):
                field.widget.attrs.update({'class': 'form-control'})
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name and ClassGroup.objects.filter(name=name, school=self.school).exists():
            raise forms.ValidationError("A class group with this name already exists.")
        return name
        
        
# students/forms.py - ADD MISSING FORMS
class EducationLevelForm(forms.ModelForm):
    """Form for creating education levels."""
    class Meta:
        model = EducationLevel
        fields = ['level', 'name', 'order', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})


class AcademicTermForm(forms.ModelForm):
    """Form for creating academic terms."""
    class Meta:
        model = AcademicTerm
        fields = ['name', 'term', 'academic_year', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError("End date must be after start date.")
        
        return cleaned_data