# users/adapters.py 
"""
CLEANED ACCOUNT ADAPTER - Using shared architecture
NO circular imports, proper error handling
"""
from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse
from django.conf import settings
from django.core.exceptions import ValidationError

# SHARED IMPORTS
from shared.constants import PARENT_PHONE_FIELD


class SchoolAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for school management system."""
    
    def is_open_for_signup(self, request):
        """
        Control whether signups are allowed.
        
        For now, allow all signups. Will be restricted later for school-specific flows.
        """
        return getattr(settings, 'ACCOUNT_ALLOW_REGISTRATION', True)
    
    def save_user(self, request, user, form, commit=True):
        """Save user with custom logic and field standardization."""
        from shared.utils import FieldMapper
        
        # Standardize form data
        form_data = FieldMapper.map_form_to_model(form.cleaned_data, 'user_registration')
        
        # Save user with standardized data
        user = super().save_user(request, user, form, commit=False)
        
        # Add custom field updates
        if PARENT_PHONE_FIELD in form_data:
            setattr(user, PARENT_PHONE_FIELD, form_data[PARENT_PHONE_FIELD])
        
        if commit:
            user.save()
        return user
    
    def get_login_redirect_url(self, request):
        """Custom login redirect based on user context."""
        # If user has a current school, redirect to dashboard
        if hasattr(request.user, 'current_school') and request.user.current_school:
            return reverse('users:dashboard')
        
        # Otherwise, redirect to school list
        return reverse('users:school_list')
    
    def clean_email(self, email):
        """Validate email with additional checks."""
        email = super().clean_email(email)
        
        # Convert to lowercase
        email = email.lower()
        
        # Check if email is from allowed domains (if configured)
        allowed_domains = getattr(settings, 'ALLOWED_EMAIL_DOMAINS', [])
        if allowed_domains:
            domain = email.split('@')[-1]
            if domain not in allowed_domains:
                raise ValidationError(
                    f"Email domain {domain} is not allowed. "
                    f"Please use an email from: {', '.join(allowed_domains)}"
                )
        
        return email
    
    def respond_user_inactive(self, request, user):
        """Custom response for inactive users."""
        from django.contrib import messages
        from django.shortcuts import redirect
        
        messages.error(
            request,
            "Your account is inactive. Please contact your school administrator."
        )
        return redirect('account_login')
    
    def pre_login(self, request, user, **kwargs):
        """Pre-login checks."""
        super().pre_login(request, user, **kwargs)
        
        # Add any pre-login logic here
        # Example: Update last login IP, log login attempt, etc.
        if hasattr(user, 'current_school') and not user.current_school:
            # Try to set current school from first profile
            try:
                Profile = apps.get_model('users', 'Profile')
                profile = Profile.objects.filter(user=user).first()
                if profile:
                    user.current_school = profile.school
                    user.save(update_fields=['current_school'])
            except Exception:
                pass
    
    def authentication_failed(self, request, **kwargs):
        """Handle authentication failures."""
        # Log failed attempts if needed
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed login attempt for email: {kwargs.get('email', 'Unknown')}")
        
        return super().authentication_failed(request, **kwargs) 