# users/forms.py - UPDATED to new architecture
"""
CLEANED USER FORMS - Using shared architecture
Consistent field naming, proper validation, NO circular imports
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.conf import settings
from django.apps import apps

# SHARED IMPORTS
from shared.constants import PARENT_PHONE_FIELD
from shared.utils import FieldMapper

# LOCAL IMPORTS ONLY
from .models import User

# Helper for lazy model loading
def _get_model(model_name, app_label='users'):
    """Get model lazily to avoid circular imports."""
    return apps.get_model(app_label, model_name)


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with email as primary identifier."""

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', PARENT_PHONE_FIELD)  # ✅ Use shared constant

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field completely
        if 'username' in self.fields:
            del self.fields['username']

        # Update widget attributes
        self.fields['email'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'your@email.com'
        })
        self.fields[PARENT_PHONE_FIELD].widget.attrs.update({  # ✅ Use shared constant
            'class': 'form-control',
            'placeholder': '+2348000000000'
        })
        self.fields['first_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()

        if not email:
            raise forms.ValidationError("Email is required")

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        # Use FieldMapper to standardize field names
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'user_creation')
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form for admin."""

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', PARENT_PHONE_FIELD, 'is_active', 'is_staff')  # ✅ Use shared constant


class SchoolOnboardingForm(forms.Form):
    """School onboarding form with HTMX validation."""

    # School Information
    school_name = forms.CharField(
        max_length=255,
        required=True,
        label="School Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter school name',
            'hx-post': '/onboarding/validate-school-name/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#school-name-validation',
            'autocomplete': 'off'
        })
    )

    subdomain = forms.SlugField(
        required=False,
        label="School Subdomain (Optional)",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'school-name',
            'hx-post': '/onboarding/check-subdomain/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#subdomain-validation',
            'autocomplete': 'off'
        })
    )

    school_type = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=True,
        label="School Type",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    contact_email = forms.EmailField(
        required=True,
        label="School Contact Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'contact@school.com'
        })
    )

    phone_number = forms.CharField(
        max_length=20,
        required=False,
        label="School Phone Number",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+234 XXX XXX XXXX'
        })
    )

    address = forms.CharField(
        required=False,
        label="School Address",
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
        label="Bank Code",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '058'
        })
    )

    account_number = forms.CharField(
        max_length=20,
        required=False,
        label="Account Number",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0123456789'
        })
    )

    account_name = forms.CharField(
        max_length=255,
        required=False,
        label="Account Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Account Holder Name'
        })
    )

    # Admin Account
    admin_first_name = forms.CharField(
        max_length=150,
        required=True,
        label="Admin First Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name'
        })
    )

    admin_last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Admin Last Name",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name'
        })
    )

    admin_email = forms.EmailField(
        required=True,
        label="Admin Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com',
            'hx-post': '/onboarding/check-email/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#email-validation',
            'autocomplete': 'off'
        })
    )

    admin_phone = forms.CharField(
        max_length=20,
        required=False,
        label="Admin Phone",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+234 XXX XXX XXXX'
        })
    )

    admin_password = forms.CharField(
        required=True,
        label="Admin Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create password',
            'hx-post': '/onboarding/validate-password/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#password-validation',
            'autocomplete': 'new-password'
        })
    )

    admin_password_confirm = forms.CharField(
        required=True,
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password',
            'autocomplete': 'new-password'
        })
    )

    # Terms agreement
    agree_terms = forms.BooleanField(
        required=True,
        label="I agree to the terms and conditions",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={'required': 'You must agree to the terms and conditions'}
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load school types from core.School model
        School = _get_model('School', 'core')
        self.fields['school_type'].choices = School.SCHOOL_TYPES

    def clean_school_name(self):
        school_name = self.cleaned_data.get('school_name', '').strip()
        if not school_name:
            raise forms.ValidationError("School name is required")

        # Check if school name already exists
        School = _get_model('School', 'core')
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
            School = _get_model('School', 'core')
            if School.objects.filter(subdomain=subdomain).exists():
                raise forms.ValidationError("This subdomain is already taken")

        return subdomain or None

    def clean_admin_email(self):
        admin_email = self.cleaned_data.get('admin_email', '').strip().lower()

        if not admin_email:
            raise forms.ValidationError("Admin email is required")

        # Check if user already exists
        if User.objects.filter(email=admin_email).exists():
            raise forms.ValidationError("A user with this email already exists")

        return admin_email

    def clean_admin_password(self):
        password = self.cleaned_data.get('admin_password')

        if password:
            if len(password) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long")

            if password.isnumeric():
                raise forms.ValidationError("Password cannot be entirely numeric")

        return password

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

        # Standardize field names using FieldMapper
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'school_onboarding')

        return cleaned_data


class StaffCreationForm(forms.ModelForm):
    """Form for creating staff members."""
    create_user_account = forms.BooleanField(
        required=False,
        initial=True,
        label="Create User Account",
        help_text="Create a user account for this staff member"
    )

    class Meta:
        model = _get_model('Staff')
        fields = [
            'first_name', 'last_name', 'gender', 'date_of_birth',
            'staff_id', 'email', PARENT_PHONE_FIELD, 'address',  # ✅ Use shared constant
            'employment_type', 'position', 'department',
            'qualification', 'notes'  # Changed from qualifications to qualification
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),  # Changed to TextInput
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        # Set placeholders and classes
        for field_name, field in self.fields.items():
            if field_name == 'create_user_account':
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.Textarea, forms.Select)):
                field.widget.attrs.update({'class': 'form-control'})

    def clean_staff_id(self):
        staff_id = self.cleaned_data.get('staff_id')
        Staff = _get_model('Staff')
        if staff_id and Staff.objects.filter(staff_id=staff_id).exists():
            raise forms.ValidationError("A staff member with this ID already exists.")
        return staff_id

    def clean_email(self):
        email = self.cleaned_data.get('email')
        Staff = _get_model('Staff')
        if email and Staff.objects.filter(email=email).exists():
            raise forms.ValidationError("A staff member with this email already exists.")
        return email

    def save(self, commit=True):
        staff = super().save(commit=False)
        if self.school:
            staff.school = self.school

        if commit:
            staff.save()
            # Create user account if requested
            if self.cleaned_data.get('create_user_account'):
                staff.create_user_account()

        return staff


class RoleCreationForm(forms.ModelForm):
    """Form for creating custom roles."""

    class Meta:
        model = _get_model('Role')
        fields = [
            'name', 'category', 'description',
            'can_manage_roles', 'can_manage_staff', 'can_manage_students',
            'can_manage_academics', 'can_manage_finances', 'can_view_reports',
            'can_communicate'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        # Update widget classes
        for field_name, field in self.fields.items():
            if field_name in ['name', 'category']:
                field.widget.attrs.update({'class': 'form-control'})
            elif field_name == 'description':
                continue  # Already set in Meta
            else:
                field.widget.attrs.update({'class': 'form-check-input'})

    def clean_name(self):
        name = self.cleaned_data.get('name')
        Role = _get_model('Role')
        if self.school and name:
            if Role.objects.filter(school=self.school, name=name).exists():
                raise forms.ValidationError("A role with this name already exists in this school.")
        return name

    def save(self, commit=True):
        role = super().save(commit=False)
        if self.school:
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


class StaffInvitationForm(forms.Form):
    """Form for inviting staff members."""
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'teacher@school.com',
            'hx-post': '/users/check-email/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#email-validation',
            'autocomplete': 'off'
        })
    )
    role = forms.ModelChoiceField(
        queryset=_get_model('Role').objects.none(),  # Will be set in __init__
        label="Role",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    message = forms.CharField(
        required=False,
        label="Personal Message (Optional)",
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
            Role = _get_model('Role')
            self.fields['role'].queryset = Role.objects.filter(
                school=self.school,
                is_active=True
            ).exclude(system_role_type='principal')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()

        if not email:
            raise forms.ValidationError("Email is required")

        # Check if user already has access to this school
        if self.school:
            Profile = _get_model('Profile')
            User = settings.AUTH_USER_MODEL
            try:
                user = User.objects.get(email=email)
                if Profile.objects.filter(user=user, school=self.school).exists():
                    raise forms.ValidationError("This user already has access to this school")
            except User.DoesNotExist:
                pass

        return email


class TeacherApplicationForm(forms.ModelForm):
    """Form for teacher applications."""
    position_id = forms.ChoiceField(
        choices=[],
        required=False,
        label="Apply for Specific Position",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = _get_model('TeacherApplication')
        fields = [
            'first_name', 'last_name', 'email', PARENT_PHONE_FIELD,  # ✅ Use shared constant
            'application_type', 'position_applied', 'years_of_experience',
            'qualification', 'specialization', 'cover_letter',
            'resume', 'certificates'
        ]
        widgets = {
            'cover_letter': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'specialization': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Mathematics, Science, English'
            }),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            PARENT_PHONE_FIELD: forms.TextInput(attrs={'class': 'form-control'}),  # ✅ Use shared constant
           'application_type': forms.Select(attrs={'class': 'form-control'}),
            'position_applied': forms.TextInput(attrs={'class': 'form-control'}),
            'years_of_experience': forms.NumberInput(attrs={'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),
            'resume': forms.FileInput(attrs={'class': 'form-control'}),
            'certificates': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school')
        super().__init__(*args, **kwargs)

        # Set position choices from school's open positions
        OpenPosition = _get_model('OpenPosition')
        positions = [(pos.id, f"{pos.title} ({pos.department})" if pos.department else pos.title)
                    for pos in OpenPosition.objects.filter(school=self.school, is_active=True)]
        positions.insert(0, ('', 'General Teacher Application'))
        self.fields['position_id'].choices = positions

        # Set position_applied choices
        position_titles = [(pos.title, pos.title)
                          for pos in OpenPosition.objects.filter(school=self.school, is_active=True)]
        if not position_titles:
            position_titles = [('Teacher', 'Teacher')]
        self.fields['position_applied'].choices = position_titles

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()

        if not email:
            raise forms.ValidationError("Email is required")

        # Check for duplicate pending applications
        TeacherApplication = _get_model('TeacherApplication')
        if TeacherApplication.objects.filter(
            school=self.school,
            email=email,
            status='pending'
        ).exists():
            raise forms.ValidationError("You already have a pending application for this school")

        return email

    def clean(self):
        cleaned_data = super().clean()
        # Standardize field names using FieldMapper
        cleaned_data = FieldMapper.map_form_to_model(cleaned_data, 'teacher_application')
        return cleaned_data


class ClassMonitorForm(forms.ModelForm):
    """Form for assigning class monitors."""

    class Meta:
        model = _get_model('ClassMonitor', 'core')
        fields = ['student', 'role', 'responsibilities', 'notes']
        widgets = {
            'responsibilities': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'List monitor responsibilities...'
            }),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'student': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.class_instance = kwargs.pop('class_instance', None)
        super().__init__(*args, **kwargs)

        # Filter students to current class
        if self.class_instance:
            Student = _get_model('Student', 'students')
            self.fields['student'].queryset = Student.objects.filter(
                current_class=self.class_instance,
                is_active=True
            ).order_by('first_name', 'last_name')
