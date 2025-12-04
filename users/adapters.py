# users/adapters.py - Custom Allauth Adapter
from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse
from core.exceptions import AuthenticationError

class SchoolAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for school management system."""
    
    def is_open_for_signup(self, request):
        """Control whether signups are allowed."""
        # For now, allow all signups. Will be restricted later for school-specific flows
        return True
    
    def save_user(self, request, user, form, commit=True):
        """Save user with custom logic."""
        user = super().save_user(request, user, form, commit=False)
        
        # Add custom validation if needed
        if commit:
            user.save()
        return user
    
    def get_login_redirect_url(self, request):
        """Custom login redirect based on user role and school."""
        # Default to dashboard, will be enhanced in later phases
        return reverse('dashboard')