# users/managers.py 
"""
CUSTOM USER MANAGER - Uses email as username
NO dependencies, clean and focused
"""
from django.contrib.auth.models import UserManager as BaseUserManager
from django.utils.translation import gettext_lazy as _

# SHARED IMPORTS
from shared.constants import PARENT_PHONE_FIELD


class UserManager(BaseUserManager):
    """
    Custom manager for User model with email as username.
    Inherits from BaseUserManager for Django auth compatibility.
    """
    
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular User with the given email and password.
        
        Args:
            email: User's email address (required)
            password: User's password (optional)
            **extra_fields: Additional user fields
        
        Returns:
            User instance
        
        Raises:
            ValueError: If email is not provided
        """
        if not email:
            raise ValueError(_('The Email must be set'))
        
        # Normalize email (lowercase domain, etc.)
        email = self.normalize_email(email)
        
        # Standardize phone field name if provided
        if 'phone' in extra_fields:
            extra_fields[PARENT_PHONE_FIELD] = extra_fields.pop('phone')
        
        # Create user instance
        user = self.model(email=email, **extra_fields)
        
        # Set password if provided
        if password:
            user.set_password(password)
        else:
            # Generate a random password if none provided
            user.set_unusable_password()
        
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        
        Args:
            email: Superuser's email address
            password: Superuser's password
            **extra_fields: Additional superuser fields
        
        Returns:
            User instance with superuser privileges
        
        Raises:
            ValueError: If is_staff or is_superuser are not True
        """
        # Set default superuser fields
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        # Validate superuser flags
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        # Create the superuser
        return self.create_user(email, password, **extra_fields)
    
    def get_by_natural_key(self, email):
        """
        Get user by natural key (email).
        Used for authentication backend.
        """
        return self.get(email=email)
    
    def create_user_from_invitation(self, invitation, user_data):
        """
        Create user from staff invitation.
        This method should be in a service, but kept here for convenience.
        
        Args:
            invitation: StaffInvitation instance
            user_data: Dictionary with user data
        
        Returns:
            User instance
        """
        from shared.utils import FieldMapper
        
        # Standardize user data
        standardized_data = FieldMapper.map_form_to_model(user_data, 'user_invitation')
        
        # Create user
        user = self.create_user(
            email=invitation.email,
            password=user_data.get('password'),
            first_name=standardized_data.get('first_name', ''),
            last_name=standardized_data.get('last_name', ''),
            **{PARENT_PHONE_FIELD: standardized_data.get(PARENT_PHONE_FIELD, '')}
        )
        
        return user
    
    def get_or_create_from_email(self, email, defaults=None):
        """
        Get or create user from email.
        
        Args:
            email: User email
            defaults: Default values for new user creation
        
        Returns:
            tuple: (user, created)
        """
        try:
            user = self.get(email=email)
            return user, False
        except self.model.DoesNotExist:
            if defaults is None:
                defaults = {}
            
            # Generate a username from email
            username = email.split('@')[0]
            
            # Create user with defaults
            user = self.create_user(
                email=email,
                username=username,
                **defaults
            )
            return user, True
    
    def get_active_users(self):
        """Get all active users."""
        return self.filter(is_active=True)
    
    def get_school_users(self, school):
        """Get all users associated with a school."""
        from django.apps import apps
        
        try:
            Profile = apps.get_model('users', 'Profile')
            profile_user_ids = Profile.objects.filter(
                school=school
            ).values_list('user_id', flat=True)
            
            return self.filter(
                id__in=profile_user_ids,
                is_active=True
            )
        except LookupError:
            # Profile model might not exist during migrations
            return self.none()
    
    def search_users(self, query):
        """
        Search users by email, name, or phone.
        
        Args:
            query: Search string
        
        Returns:
            QuerySet of matching users
        """
        from django.db.models import Q
        
        return self.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(**{f'{PARENT_PHONE_FIELD}__icontains': query})  # ✅ Use shared constant
        ).filter(is_active=True)