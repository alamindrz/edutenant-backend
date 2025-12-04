# users/forms.py - UPDATED
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, School, SchoolOnboardingTemplate, Staff, Role, TeacherApplication
from core.models import ClassMonitor

class ClassMonitorForm(forms.ModelForm):
    """Form for assigning class monitors."""
    class Meta:
        model = ClassMonitor
        fields = ['student', 'role', 'responsibilities', 'notes']
        widgets = {
            'responsibilities': forms.Textarea(attrs={'rows': 3, 'placeholder': 'List monitor responsibilities...'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        self.class_instance = kwargs.pop('class_instance', None)
        super().__init__(*args, **kwargs)
        
        # Filter students to current class
        if self.class_instance:
            from students.models import Student
            self.fields['student'].queryset = Student.objects.filter(
                current_class=self.class_instance, 
                is_active=True
            )
        
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})



class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with email as primary identifier."""
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field completely
        if 'username' in self.fields:
            del self.fields['username']
        
        self.fields['email'].widget.attrs.update({'placeholder': 'your@email.com'})
        self.fields['phone_number'].widget.attrs.update({'placeholder': '+2348000000000'})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            if User.objects.filter(email=email).exists():
                raise forms.ValidationError("A user with this email already exists.")
        return email

class CustomUserChangeForm(UserChangeForm):
    """Custom user change form for admin."""
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone_number', 'is_active', 'is_staff')

class SchoolCreationForm(forms.ModelForm):
    """Form for creating new schools during onboarding."""
    
    class Meta:
        model = School
        fields = ('name', 'subdomain', 'primary_color', 'secondary_color')
        widgets = {
            'primary_color': forms.TextInput(attrs={'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color'}),
        }

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain')
        if subdomain:
            if School.objects.filter(subdomain=subdomain).exists():
                raise forms.ValidationError("This subdomain is already taken. Please choose another.")
            
            # Validate subdomain format
            if not subdomain.replace('-', '').replace('_', '').isalnum():
                raise forms.ValidationError("Subdomain can only contain letters, numbers, hyphens, and underscores.")
            
            if len(subdomain) < 3:
                raise forms.ValidationError("Subdomain must be at least 3 characters long.")
                
        return subdomain
        
        
        


# users/forms.py - ENHANCED VERSION
class SchoolOnboardingForm(forms.Form):
    # School Information
    school_name = forms.CharField(
        max_length=255, 
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Enter school name',
            'hx-post': '/onboarding/validate-school-name/',
            'hx-trigger': 'change',
            'hx-target': '#school-name-validation'
        })
    )
    
    subdomain = forms.SlugField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'school-name',
            'hx-post': '/onboarding/check-subdomain/',
            'hx-trigger': 'change',
            'hx-target': '#subdomain-validation'
        })
    )
    
    school_type = forms.ChoiceField(
        choices=School.SCHOOL_TYPES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    contact_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@school.com'})
    )
    
    phone_number = forms.CharField(
        max_length=20, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 XXX XXX XXXX'})
    )
    
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 
            'rows': 3, 
            'placeholder': 'School physical address'
        })
    )
    
    # Bank Details (Optional)
    bank_code = forms.CharField(
        max_length=10, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '058'})
    )
    
    account_number = forms.CharField(
        max_length=20, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0123456789'})
    )
    
    account_name = forms.CharField(
        max_length=255, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account Holder Name'})
    )
    
    # Admin Account
    admin_first_name = forms.CharField(
        max_length=150, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'})
    )
    
    admin_last_name = forms.CharField(
        max_length=150, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'})
    )
    
    admin_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control', 
            'placeholder': 'your@email.com',
            'hx-post': '/onboarding/check-email/',
            'hx-trigger': 'change',
            'hx-target': '#email-validation'
        })
    )
    
    admin_phone = forms.CharField(
        max_length=20, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 XXX XXX XXXX'})
    )
    
    admin_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Create password',
            'hx-post': '/onboarding/validate-password/',
            'hx-trigger': 'change',
            'hx-target': '#password-validation'
        })
    )
    
    admin_password_confirm = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'})
    )
    
    # Terms agreement - FIXED
    agree_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={'required': 'You must agree to the terms and conditions'}
    )
    
    def clean_school_name(self):
        school_name = self.cleaned_data.get('school_name', '').strip()
        if not school_name:
            raise forms.ValidationError("School name is required")
        
        # Check if school name already exists
        from .models import School
        if School.objects.filter(name__iexact=school_name).exists():
            raise forms.ValidationError("A school with this name already exists")
            
        return school_name
    
    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain', '').strip().lower()
        
        if subdomain:
            # Validate format
            if len(subdomain) < 3:
                raise forms.ValidationError("Subdomain must be at least 3 characters long")
            
            if not subdomain.replace('-', '').isalnum():
                raise forms.ValidationError("Subdomain can only contain letters, numbers, and hyphens")
            
            if subdomain.startswith('-') or subdomain.endswith('-'):
                raise forms.ValidationError("Subdomain cannot start or end with a hyphen")
            
            # Check availability
            from .models import School
            if School.objects.filter(subdomain=subdomain).exists():
                raise forms.ValidationError("This subdomain is already taken")
        
        return subdomain or None
    
    def clean_admin_email(self):
        admin_email = self.cleaned_data.get('admin_email', '').strip().lower()
        
        if not admin_email:
            raise forms.ValidationError("Admin email is required")
        
        # Check if user already exists
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(email=admin_email).exists():
            raise forms.ValidationError("A user with this email already exists")
            
        return admin_email
    
    def clean_admin_password(self):
        password = self.cleaned_data.get('admin_password')
        
        if password:
            if len(password) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long")
            
            # Add more password strength checks if needed
            if password.isnumeric():
                raise forms.ValidationError("Password cannot be entirely numeric")
                
        return password
    
    def clean_agree_terms(self):
        agree_terms = self.cleaned_data.get('agree_terms')
        if not agree_terms:
            raise forms.ValidationError("You must agree to the terms and conditions")
        return agree_terms
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Password confirmation
        admin_password = cleaned_data.get('admin_password')
        admin_password_confirm = cleaned_data.get('admin_password_confirm')
        
        if admin_password and admin_password_confirm:
            if admin_password != admin_password_confirm:
                self.add_error('admin_password_confirm', "Passwords do not match")
        
        # Bank details validation
        bank_code = cleaned_data.get('bank_code')
        account_number = cleaned_data.get('account_number')
        account_name = cleaned_data.get('account_name')
        
        # If any bank detail is provided, all must be provided
        if any([bank_code, account_number, account_name]):
            if not all([bank_code, account_number, account_name]):
                self.add_error('bank_code', "All bank details are required if you provide any")
        
        return cleaned_data
        
        
        
class StaffCreationForm(forms.ModelForm):
    """Form for creating staff members."""
    create_user_account = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Create a user account for this staff member"
    )
    
    class Meta:
        model = Staff
        fields = [
            'first_name', 'last_name', 'gender', 'date_of_birth',
            'staff_id', 'email', 'phone_number', 'address',
            'employment_type', 'position', 'department',
            'qualifications', 'notes'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'qualifications': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        # Set placeholders and classes
        for field_name, field in self.fields.items():
            if isinstance(field, forms.CharField):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field, forms.EmailField):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field, forms.ChoiceField):
                field.widget.attrs.update({'class': 'form-control'})
    
    def clean_staff_id(self):
        staff_id = self.cleaned_data.get('staff_id')
        if staff_id and Staff.objects.filter(staff_id=staff_id).exists():
            raise forms.ValidationError("A staff member with this ID already exists.")
        return staff_id
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and Staff.objects.filter(email=email).exists():
            raise forms.ValidationError("A staff member with this email already exists.")
        return email

class RoleCreationForm(forms.ModelForm):
    """Form for creating custom roles."""
    class Meta:
        model = Role
        fields = [
            'name', 'category', 'description',
            'can_manage_roles', 'can_manage_staff', 'can_manage_students',
            'can_manage_academics', 'can_manage_finances', 'can_view_reports',
            'can_communicate'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
    
    def save(self, commit=True):
        role = super().save(commit=False)
        role.school = self.school
        role.is_system_role = False
        
        # Build permissions list from boolean fields
        permissions = []
        if role.can_manage_roles:
            permissions.append('manage_roles')
        if role.can_manage_staff:
            permissions.append('manage_staff')
        if role.can_manage_students:
            permissions.append('manage_students')
        if role.can_manage_academics:
            permissions.append('manage_academics')
        if role.can_manage_finances:
            permissions.append('manage_finances')
        if role.can_view_reports:
            permissions.append('view_reports')
        if role.can_communicate:
            permissions.append('communicate')
        
        role.permissions = permissions
        
        if commit:
            role.save()
        return role
        
        
# users/forms.py - ADD INVITATION FORM

class StaffInvitationForm(forms.Form):
    """Form for inviting staff members."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'teacher@school.com',
            'hx-post': '/users/check-email/',  # HTMX email validation
            'hx-trigger': 'change',
            'hx-target': '#email-validation'
        })
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),  # Will be set in __init__
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional personal message...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        if self.school:
            self.fields['role'].queryset = Role.objects.filter(
                school=self.school, 
                is_active=True
            ).exclude(system_role_type='principal')
            



class TeacherApplicationForm(forms.ModelForm):
    """Form for teacher applications."""
    position_id = forms.ChoiceField(choices=[], required=False, label="Apply for specific position")
    
    class Meta:
        model = TeacherApplication
        fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'application_type', 'position_applied', 'years_of_experience',
            'qualification', 'specialization', 'cover_letter',
            'resume', 'certificates'
        ]
        widgets = {
            'cover_letter': forms.Textarea(attrs={'rows': 4}),
            'specialization': forms.TextInput(attrs={'placeholder': 'e.g., Mathematics, Science, English'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school')
        super().__init__(*args, **kwargs)
        
        # Set position choices from school's open positions
        positions = [(pos.id, f"{pos.title} ({pos.department})" if pos.department else pos.title) 
                    for pos in self.school.openposition_set.filter(is_active=True)]
        positions.insert(0, ('', 'General Teacher Application'))
        self.fields['position_id'].choices = positions
        
        # Set position_applied choices
        position_titles = [(pos.title, pos.title) for pos in self.school.openposition_set.filter(is_active=True)]
        if not position_titles:
            position_titles = [('Teacher', 'Teacher')]
        self.fields['position_applied'].choices = position_titles