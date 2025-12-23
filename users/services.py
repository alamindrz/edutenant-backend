# users/services.py
"""
CLEANED USER SERVICES - Using shared architecture
NO circular imports, NO code duplication, PROPER logging
"""
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.apps import apps
from django.core.exceptions import ValidationError as DjangoValidationError

# SHARED IMPORTS
from shared.exceptions.payment import PaymentProcessingError
from shared.services.payment.payment import PaymentCoreService
from shared.constants import StatusChoices, PARENT_PHONE_FIELD
from shared.utils.field_mapping import FieldMapper

from django.contrib.auth import get_user_model





class SchoolOnboardingError(Exception):
    """Exception raised during school onboarding."""
    
    def __init__(self, message, user_friendly=False, details=None):
        self.message = message
        self.user_friendly = user_friendly
        self.details = details
        super().__init__(self.message)


class ValidationError(DjangoValidationError):
    """Extended validation error with user-friendly messages."""
    
    def __init__(self, message, user_friendly=False, field=None):
        self.user_friendly = user_friendly
        self.field = field
        super().__init__(message)


logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name, app_label='users'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def _get_or_create_user(email, user_data=None):
    """Get or create user with proper defaults."""
    User = get_user_model()
    
    try:
        user = User.objects.get(email=email)
        # Update user data if provided
        if user_data:
            for field in ['first_name', 'last_name', 'phone_number']:
                if field in user_data and user_data[field]:
                    setattr(user, field, user_data[field])
            user.save()
        return user, False
    except User.DoesNotExist:
        if not user_data:
            user_data = {}
        
        # Generate username from email if not provided
        username = user_data.get('username', email)
        
        user = User.objects.create_user(
            email=email,
            username=username,
            password=user_data.get('password', User.objects.make_random_password()),
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            phone_number=user_data.get(PARENT_PHONE_FIELD, ''),
        )
        return user, True


# ============ EMAIL SERVICE ============

class EmailService:
    """Service for handling email communications using shared architecture."""
    
    @staticmethod
    def send_template_email(subject: str, template_name: str, context: Dict, 
                           recipient_list: List[str], fail_silently: bool = False) -> bool:
        """
        Generic method for sending template-based emails.
        
        Args:
            subject: Email subject
            template_name: Template path without extension
            context: Template context
            recipient_list: List of recipient emails
            fail_silently: Whether to suppress exceptions
            
        Returns:
            bool: True if email sent successfully
        """
        try:
            html_message = render_to_string(f'{template_name}.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                recipient_list,
                html_message=html_message,
                fail_silently=fail_silently
            )
            
            logger.info(f"Email sent successfully to {len(recipient_list)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}", exc_info=True)
            if not fail_silently:
                raise
            return False
    
    @staticmethod
    def send_welcome_email(school, admin_user):
        """Send welcome email to school admin."""
        try:
            subject = f"Welcome to Edusuite - {school.name} is Ready!"
            
            context = {
                'school': school,
                'admin_user': admin_user,
                'login_url': settings.LOGIN_URL if hasattr(settings, 'LOGIN_URL') else '/accounts/login/',
                'dashboard_url': '/dashboard/',
                'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@edusuite.com'),
            }
            
            EmailService.send_template_email(
                subject=subject,
                template_name='emails/welcome_school',
                context=context,
                recipient_list=[admin_user.email]
            )
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {admin_user.email}: {str(e)}")
            # Don't raise - email failure shouldn't break onboarding
    
    @staticmethod
    def send_invitation_email(invitation):
        """Send invitation email to potential staff member."""
        try:
            subject = f"Invitation to join {invitation.school.name}"
            
            context = {
                'invitation': invitation,
                'accept_url': f"{settings.BASE_URL}/invitations/accept/{invitation.token}/",
                'school': invitation.school,
                'role': invitation.role,
            }
            
            EmailService.send_template_email(
                subject=subject,
                template_name='emails/staff_invitation',
                context=context,
                recipient_list=[invitation.email]
            )
            
        except Exception as e:
            logger.error(f"Failed to send invitation email to {invitation.email}: {str(e)}")
            raise ValidationError("Failed to send invitation email", user_friendly=True)
    
    @staticmethod
    def send_application_notification(application, admin_users):
        """Send notification about new teacher application to school admins."""
        try:
            subject = f"New Teacher Application for {application.school.name}"
            
            admin_emails = [admin.email for admin in admin_users if admin.email]
            if not admin_emails:
                logger.warning(f"No admin emails found for school {application.school.name}")
                return
            
            context = {
                'application': application,
                'review_url': f"{settings.BASE_URL}/admin/applications/{application.id}/review/",
            }
            
            EmailService.send_template_email(
                subject=subject,
                template_name='emails/new_application',
                context=context,
                recipient_list=admin_emails,
                fail_silently=True  # Don't fail entire process if one email fails
            )
            
        except Exception as e:
            logger.error(f"Failed to send application notifications: {str(e)}")


# ============ VALIDATION SERVICE ============

class ValidationService:
    """Service for data validation using shared constants."""
    
    @staticmethod
    def validate_subdomain(subdomain: str) -> tuple:
        """
        Validate subdomain format and availability.
        
        Args:
            subdomain: Subdomain string to validate
            
        Returns:
            tuple: (is_valid: bool, suggestions: List[str])
        """
        if not subdomain:
            return True, []  # Empty subdomain is valid (means no subdomain)
        
        # Format validation
        if len(subdomain) < 3:
            raise ValidationError("Subdomain must be at least 3 characters long", user_friendly=True)
        
        if not subdomain.replace('-', '').isalnum():
            raise ValidationError("Subdomain can only contain letters, numbers, and hyphens", user_friendly=True)
        
        if subdomain.startswith('-') or subdomain.endswith('-'):
            raise ValidationError("Subdomain cannot start or end with a hyphen", user_friendly=True)
        
        # Availability check
        School = _get_model('School', 'core')
        if School.objects.filter(subdomain=subdomain).exists():
            return False, SchoolOnboardingService.get_subdomain_suggestions(subdomain)
        
        return True, []
    
    @staticmethod
    def validate_onboarding_data(data: Dict) -> None:
        """Validate school onboarding data."""
        required_fields = ['school_name', 'school_type', 'contact_email', 'admin_email', 'admin_password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}", user_friendly=True)
        
        # Email validation
        if data.get('admin_email') and data.get('contact_email'):
            if data['admin_email'] == data['contact_email']:
                raise ValidationError("Admin email and contact email cannot be the same", user_friendly=True)
        
        # Password strength (basic check)
        if len(data['admin_password']) < 8:
            raise ValidationError("Password must be at least 8 characters long", user_friendly=True)
        
        # School type validation
        valid_school_types = ['nursery', 'primary', 'secondary', 'combined', 'full']
        if data.get('school_type') and data['school_type'] not in valid_school_types:
            raise ValidationError(f"Invalid school type. Must be one of: {', '.join(valid_school_types)}", user_friendly=True)
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format and basic structure."""
        if not email or '@' not in email or '.' not in email:
            raise ValidationError("Invalid email address", user_friendly=True)
        return True
    
    @staticmethod
    def validate_password(password: str, confirm_password: Optional[str] = None) -> bool:
        """Validate password strength."""
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long", user_friendly=True)
        
        if password.isnumeric():
            raise ValidationError("Password cannot be entirely numeric", user_friendly=True)
        
        if confirm_password and password != confirm_password:
            raise ValidationError("Passwords do not match", user_friendly=True)
        
        return True


# ============ SCHOOL ONBOARDING SERVICE ============

class SchoolOnboardingService:
    """Complete service for automating school onboarding and configuration."""
    
    # Template configurations
    _SCHOOL_TEMPLATES = {
        'nursery': {
            'roles': [
                {
                    'name': 'Principal',
                    'category': 'administration',
                    'system_role_type': 'principal',
                    'description': 'School principal with full administrative access',
                    'permissions': ['*'],
                    'can_manage_roles': True,
                    'can_manage_staff': True,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': True,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
                {
                    'name': 'Teacher',
                    'category': 'academic',
                    'system_role_type': 'teacher',
                    'description': 'Teaching staff with academic permissions',
                    'permissions': ['manage_attendance', 'manage_scores', 'view_reports', 'communicate'],
                    'can_manage_roles': False,
                    'can_manage_staff': False,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': False,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
            ]
        },
        'primary': {
            'roles': [
                {
                    'name': 'Principal',
                    'category': 'administration',
                    'system_role_type': 'principal',
                    'description': 'School principal with full administrative access',
                    'permissions': ['*'],
                    'can_manage_roles': True,
                    'can_manage_staff': True,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': True,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
                {
                    'name': 'Teacher',
                    'category': 'academic',
                    'system_role_type': 'teacher',
                    'description': 'Teaching staff with academic permissions',
                    'permissions': ['manage_attendance', 'manage_scores', 'view_reports', 'communicate'],
                    'can_manage_roles': False,
                    'can_manage_staff': False,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': False,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
            ]
        },
        'secondary': {
            'roles': [
                {
                    'name': 'Principal',
                    'category': 'administration',
                    'system_role_type': 'principal',
                    'description': 'School principal with full administrative access',
                    'permissions': ['*'],
                    'can_manage_roles': True,
                    'can_manage_staff': True,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': True,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
                {
                    'name': 'Teacher',
                    'category': 'academic',
                    'system_role_type': 'teacher',
                    'description': 'Teaching staff with academic permissions',
                    'permissions': ['manage_attendance', 'manage_scores', 'view_reports', 'communicate'],
                    'can_manage_roles': False,
                    'can_manage_staff': False,
                    'can_manage_students': True,
                    'can_manage_academics': True,
                    'can_manage_finances': False,
                    'can_view_reports': True,
                    'can_communicate': True,
                },
            ]
        },
    }
    
    @staticmethod
    @transaction.atomic
    def create_school_from_template(onboarding_data: Dict):
        """
        Create a complete school from template configuration.
        
        Args:
            onboarding_data: School creation data
            
        Returns:
            School: Created school instance
            
        Raises:
            SchoolOnboardingError: If onboarding fails
        """
        logger.info("Starting school onboarding process", extra={'school_name': onboarding_data.get('school_name')})
        
        try:
            # Step 1: Validate input data
            ValidationService.validate_onboarding_data(onboarding_data)
            
            # Step 2: Check if admin user already exists
            User = get_user_model()
            admin_email = onboarding_data['admin_email']
            if User.objects.filter(email=admin_email).exists():
                raise SchoolOnboardingError(
                    f"User with email {admin_email} already exists.",
                    user_friendly=True
                )
            
            # Step 3: Create school record
            school = SchoolOnboardingService._create_school_record(onboarding_data)
            
            # Step 4: Apply configuration template
            SchoolOnboardingService._apply_configuration_template(school, onboarding_data['school_type'])
            
            # Step 5: Create admin user
            admin_user = SchoolOnboardingService._create_school_admin(school, onboarding_data)
            
            # Step 6: Set up classes using shared ClassManager (non-critical)
            try:
                SchoolOnboardingService._setup_default_classes(school, onboarding_data['school_type'])
            except Exception as e:
                logger.warning(f"Class creation failed but continuing: {e}")
            
            # Step 7: Send welcome email (non-critical)
            try:
                EmailService.send_welcome_email(school, admin_user)
            except Exception as e:
                logger.warning(f"Welcome email failed but continuing: {e}")
            
            logger.info("School onboarding completed successfully", extra={'school_id': school.id})
            return school
            
        except Exception as e:
            logger.error("School onboarding failed", extra={'error': str(e)}, exc_info=True)
            # Clean up any partially created data
            SchoolOnboardingService._cleanup_failed_onboarding(locals())
            raise SchoolOnboardingError(f"School creation failed: {str(e)}", user_friendly=True)
    
    
    @staticmethod
    def _create_school_record(onboarding_data: Dict):
        """Create the school database record."""
        try:
            School = _get_model('School', 'core')
            
            # Handle subdomain (could be None, empty string, or actual value)
            subdomain = onboarding_data.get('subdomain', '')
            if subdomain:  # Check if it's truthy (not None and not empty)
                subdomain = subdomain.strip()
            else:
                subdomain = None  # Set to None for database
            
            subdomain_status = 'none'  # Default to no subdomain
            
            # Determine subdomain status
            if subdomain:
                subdomain_status = 'active'  # Auto-activate for now
            
            school = School.objects.create(
                name=onboarding_data['school_name'],
                subdomain=subdomain,  # Could be None or cleaned string
                school_type=onboarding_data['school_type'],
                contact_email=onboarding_data['contact_email'],
                phone_number=onboarding_data.get(PARENT_PHONE_FIELD),  # ✅ Use shared constant
                address=onboarding_data.get('address'),
                bank_code=onboarding_data.get('bank_code'),
                account_number=onboarding_data.get('account_number'),
                account_name=onboarding_data.get('account_name'),
                subdomain_status=subdomain_status,
                subdomain_expires_at=timezone.now() + timedelta(days=30) if subdomain else None,
                onboarding_completed=True
            )
            
            logger.info(f"Created school record: {school.name}")
            return school
            
        except Exception as e:
            logger.error(f"Failed to create school record: {e}", exc_info=True)
            raise SchoolOnboardingError("Failed to create school record")
    
    @staticmethod
    def _apply_configuration_template(school, school_type: str):
        """Apply pre-configured template based on school type."""
        try:
            Role = _get_model('Role')
            template_config = SchoolOnboardingService._SCHOOL_TEMPLATES.get(
                school_type, 
                SchoolOnboardingService._SCHOOL_TEMPLATES['primary']  # Default fallback
            )
            
            for role_config in template_config['roles']:
                Role.objects.create(
                    name=role_config['name'],
                    category=role_config['category'],
                    school=school,
                    permissions=role_config['permissions'],
                    is_system_role=True,
                    system_role_type=role_config.get('system_role_type'),
                    description=role_config['description'],
                    can_manage_roles=role_config.get('can_manage_roles', False),
                    can_manage_staff=role_config.get('can_manage_staff', False),
                    can_manage_students=role_config.get('can_manage_students', False),
                    can_manage_academics=role_config.get('can_manage_academics', False),
                    can_manage_finances=role_config.get('can_manage_finances', False),
                    can_view_reports=role_config.get('can_view_reports', False),
                    can_communicate=role_config.get('can_communicate', False),
                )
            
            logger.info(f"School template applied successfully for school {school.id}")
            
        except Exception as e:
            logger.error(f"Failed to apply school template: {e}", exc_info=True)
            raise SchoolOnboardingError("Failed to apply school template") from e
    
    @staticmethod
    def _create_school_admin(school, onboarding_data: Dict):
        """Create school admin user and principal role."""
        try:
            User = get_user_model()
            Role = _get_model('Role')
            Profile = _get_model('Profile')
            
            # Create admin user
            admin_user = User.objects.create_user(
                email=onboarding_data['admin_email'],
                username=onboarding_data['admin_email'],
                password=onboarding_data['admin_password'],
                first_name=onboarding_data.get('admin_first_name', 'School'),
                last_name=onboarding_data.get('admin_last_name', 'Admin'),
                phone_number=onboarding_data.get(PARENT_PHONE_FIELD),  # ✅ Use shared constant
            )
            
            # Get principal role
            principal_role = Role.objects.get(
                school=school,
                system_role_type='principal'
            )
            
            # Create profile
            Profile.objects.create(
                user=admin_user,
                school=school,
                role=principal_role,
                phone_number=onboarding_data.get(PARENT_PHONE_FIELD),  # ✅ Use shared constant
            )
            
            # Set current school
            admin_user.current_school = school
            admin_user.save()
            
            logger.info(f"School admin created successfully: {admin_user.email}")
            return admin_user
            
        except Exception as e:
            logger.error(f"Failed to create school admin: {e}", exc_info=True)
            # Clean up user if created
            if 'admin_user' in locals() and admin_user.id:
                admin_user.delete()
            raise SchoolOnboardingError("Failed to create school administrator") from e
    
    @staticmethod
    def _setup_default_classes(school, school_type: str):
        """Set up default classes for school."""
        try:
            from core.models import Class
            
            # Define class templates based on school type
            class_templates = {
                'nursery': ['Playgroup', 'Nursery 1', 'Nursery 2', 'Reception'],
                'primary': ['Primary 1', 'Primary 2', 'Primary 3', 'Primary 4', 'Primary 5', 'Primary 6'],
                'secondary': ['JSS 1', 'JSS 2', 'JSS 3', 'SSS 1', 'SSS 2', 'SSS 3'],
                'combined': ['Primary 1', 'Primary 2', 'JSS 1', 'JSS 2', 'SSS 1'],
                'full': ['Playgroup', 'Nursery 1', 'Primary 1', 'Primary 6', 'JSS 1', 'SSS 3'],
            }
            
            classes = class_templates.get(school_type, class_templates['primary'])
            
            for i, class_name in enumerate(classes, 1):
                Class.objects.create(
                    school=school,
                    name=class_name,
                    code=f"CLS{school.id:03d}{i:02d}",
                    capacity=30,
                    academic_year=timezone.now().year,
                    is_active=True,
                )
            
            logger.info(f"Created {len(classes)} classes for school {school.name}")
            
        except Exception as e:
            logger.error(f"Failed to create default classes: {e}")
            raise
    
    @staticmethod
    def _cleanup_failed_onboarding(local_vars: Dict):
        """Clean up partially created data from failed onboarding."""
        try:
            if 'school' in local_vars and local_vars['school']:
                local_vars['school'].delete()
                logger.info("Cleaned up partially created school due to onboarding failure")
        except Exception as e:
            logger.error(f"Failed to clean up onboarding data: {e}")
    
    @staticmethod
    def is_subdomain_available(subdomain: str) -> bool:
        """Check if subdomain is available."""
        School = _get_model('School', 'core')
        if not subdomain or subdomain.strip() == '':
            # Empty subdomain is always "available" (means no subdomain)
            return True
        return not School.objects.filter(subdomain=subdomain.strip()).exists()
    
    @staticmethod
    def get_subdomain_suggestions(requested_subdomain: str) -> List[str]:
        """Get alternative subdomain suggestions when requested is unavailable."""
        School = _get_model('School', 'core')
        suggestions = []
        base = requested_subdomain.strip()
        
        if not base:
            return suggestions
        
        # Try different variations
        variations = [
            f"{base}1",
            f"{base}school",
            f"{base}-academy",
            f"{base}2024",
            f"my{base}",
            f"{base}edu",
            f"the{base}",
        ]
        
        for variation in variations:
            if not School.objects.filter(subdomain=variation).exists():
                suggestions.append(variation)
            if len(suggestions) >= 3:
                break
        
        return suggestions
        

# ============ ROLE MANAGEMENT SERVICE ============

class RoleManagementService:
    """Service for role management operations."""
    
    @staticmethod
    def create_custom_role(school, role_data: Dict):
        """Create custom role with permissions."""
        try:
            Role = _get_model('Role')
            
            # Build permissions list from boolean fields
            permissions = []
            permission_map = {
                'can_manage_roles': 'manage_roles',
                'can_manage_staff': 'manage_staff',
                'can_manage_students': 'manage_students',
                'can_manage_academics': 'manage_academics',
                'can_manage_finances': 'manage_finances',
                'can_view_reports': 'view_reports',
                'can_communicate': 'communicate',
            }
            
            for field, permission in permission_map.items():
                if role_data.get(field):
                    permissions.append(permission)
            
            role = Role.objects.create(
                name=role_data['name'],
                category=role_data['category'],
                school=school,
                description=role_data.get('description', ''),
                permissions=permissions,
                is_system_role=False,
                can_manage_roles=role_data.get('can_manage_roles', False),
                can_manage_staff=role_data.get('can_manage_staff', False),
                can_manage_students=role_data.get('can_manage_students', False),
                can_manage_academics=role_data.get('can_manage_academics', False),
                can_manage_finances=role_data.get('can_manage_finances', False),
                can_view_reports=role_data.get('can_view_reports', False),
                can_communicate=role_data.get('can_communicate', False),
            )
            
            logger.info(f"Custom role created successfully: {role.name} for school {school.id}")
            return role
            
        except Exception as e:
            logger.error(f"Failed to create custom role for school {school.id}: {str(e)}")
            raise
    
    @staticmethod
    def update_role_permissions(role, permission_data: Dict):
        """Update role permissions."""
        try:
            permission_map = {
                'can_manage_roles': 'manage_roles',
                'can_manage_staff': 'manage_staff',
                'can_manage_students': 'manage_students',
                'can_manage_academics': 'manage_academics',
                'can_manage_finances': 'manage_finances',
                'can_view_reports': 'view_reports',
                'can_communicate': 'communicate',
            }
            
            permissions = []
            for field, permission in permission_map.items():
                if permission_data.get(field):
                    permissions.append(permission)
                    setattr(role, field, True)
                else:
                    setattr(role, field, False)
            
            role.permissions = permissions
            role.save()
            
            logger.info(f"Role permissions updated for: {role.name}")
            return role
            
        except Exception as e:
            logger.error(f"Failed to update role permissions: {str(e)}")
            raise


# ============ STAFF SERVICE ============

class StaffService:
    """Unified service for all staff-related operations."""
    
    @staticmethod
    def generate_staff_id(school) -> str:
        """Generate unique staff ID for school."""
        Staff = _get_model('Staff')
        
        last_staff = Staff.objects.filter(school=school).order_by('-id').first()
        if last_staff and last_staff.staff_id:
            try:
                # Extract numeric part and increment
                import re
                match = re.search(r'(\d+)$', last_staff.staff_id)
                if match:
                    next_num = int(match.group(1)) + 1
                    return f"STAFF{next_num:04d}"
            except (ValueError, AttributeError):
                pass
        
        # Default format
        school_code = school.subdomain.upper()[:3] if school.subdomain else 'SCH'
        year = timezone.now().year
        return f"{school_code}/STAFF/{year}/0001"
    
    @staticmethod
    @transaction.atomic
    def invite_teacher(school, invited_by, email: str, role_id: int, message: str = "") -> Any:
        """Invite a teacher to join the school."""
        try:
            ValidationService.validate_email(email)
            
            Role = _get_model('Role')
            StaffInvitation = _get_model('StaffInvitation')
            Profile = _get_model('Profile')
            User = get_user_model()
            
            # Check if user already exists and has access
            existing_user = User.objects.filter(email=email).first()
            if existing_user:
                if Profile.objects.filter(user=existing_user, school=school).exists():
                    raise ValidationError(f"{email} already has access to {school.name}", user_friendly=True)
            
            # Get role
            role = Role.objects.get(id=role_id, school=school)
            
            # Check for existing pending invitation
            existing_invitation = StaffInvitation.objects.filter(
                school=school, email=email, status='pending'
            ).first()
            
            if existing_invitation:
                if existing_invitation.is_valid():
                    raise ValidationError(f"An invitation is already pending for {email}", user_friendly=True)
                else:
                    # Mark expired invitation as expired
                    existing_invitation.status = 'expired'
                    existing_invitation.save()
            
            # Create invitation
            token = secrets.token_urlsafe(32)
            expires_at = timezone.now() + timedelta(days=7)
            
            invitation = StaffInvitation.objects.create(
                school=school,
                email=email,
                role=role,
                invited_by=invited_by,
                token=token,
                expires_at=expires_at,
                message=message
            )
            
            # Send invitation email
            EmailService.send_invitation_email(invitation)
            
            logger.info(f"Teacher invitation sent to {email} for school {school.name}")
            return invitation
            
        except Exception as e:
            logger.error(f"Failed to invite teacher: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    @transaction.atomic
    def accept_invitation(token: str, user_data: Dict) -> Any:
        """Accept invitation and create teacher account."""
        try:
            StaffInvitation = _get_model('StaffInvitation')
            Profile = _get_model('Profile')
            Role = _get_model('Role')
            Staff = _get_model('Staff')
            
            invitation = StaffInvitation.objects.get(token=token, status='pending')
            
            if not invitation.is_valid():
                raise ValidationError("Invitation has expired or is no longer valid", user_friendly=True)
            
            # Validate user data
            ValidationService.validate_password(user_data['password'], user_data.get('password_confirm'))
            
            # Get or create user
            user, created = _get_or_create_user(
                invitation.email,
                {
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                    PARENT_PHONE_FIELD: user_data.get(PARENT_PHONE_FIELD, ''),  # ✅ Use shared constant
                    'password': user_data['password'],
                }
            )
            
            # Create profile
            Profile.objects.create(
                user=user,
                school=invitation.school,
                role=invitation.role
            )
            
            # Update user's current school
            user.current_school = invitation.school
            user.save()
            
            # Mark invitation as accepted
            invitation.status = 'accepted'
            invitation.save()
            
            # Create staff record
            staff, staff_created = Staff.objects.get_or_create(
                school=invitation.school,
                email=invitation.email,
                defaults={
                    'user': user,
                    'staff_id': StaffService.generate_staff_id(invitation.school),
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    PARENT_PHONE_FIELD: user_data.get(PARENT_PHONE_FIELD, ''),  # ✅ Use shared constant
                    'position': invitation.role.name,
                    'employment_type': 'full_time',
                    'date_joined': timezone.now().date(),
                    'is_teaching_staff': True,
                }
            )
            
            logger.info(f"Teacher onboarding completed: {user.email} for school {invitation.school.name}")
            return user
            
        except StaffInvitation.DoesNotExist:
            raise ValidationError("Invalid invitation token", user_friendly=True)
        except Exception as e:
            logger.error(f"Failed to accept invitation: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    @transaction.atomic
    def approve_application(application, approved_by):
        """Approve a teacher application and create staff record."""
        try:
            Profile = _get_model('Profile')
            Role = _get_model('Role')
            Staff = _get_model('Staff')
            
            with transaction.atomic():
                # Get or create user account
                user, created = _get_or_create_user(
                    application.email,
                    {
                        'first_name': application.first_name,
                        'last_name': application.last_name,
                        PARENT_PHONE_FIELD: application.phone_number,  # ✅ Use shared constant
                    }
                )
                
                if created:
                    # Generate temporary password
                    temp_password = User.objects.make_random_password()
                    user.set_password(temp_password)
                    user.save()
                
                # Get teacher role
                teacher_role = StaffService._get_teacher_role(application.school)
                
                # Create profile
                profile, profile_created = Profile.objects.get_or_create(
                    user=user,
                    school=application.school,
                    defaults={'role': teacher_role}
                )
                
                if not profile_created:
                    profile.role = teacher_role
                    profile.save()
                
                # Update user's current school
                user.current_school = application.school
                user.save()
                
                # Create staff record
                staff = StaffService._create_staff_from_application(application, user, teacher_role)
                
                # Update application status
                application.status = StatusChoices.APPROVED  # ✅ Use shared constant
                application.status_changed_by = approved_by
                application.status_changed_at = timezone.now()
                application.applicant = user
                application.save()
                
                logger.info(f"Teacher application approved and staff created: {staff.full_name}")
                return staff
                
        except Exception as e:
            logger.error(f"Failed to approve teacher application: {str(e)}", exc_info=True)
            raise


    @staticmethod
    def _get_teacher_role(school):
        """Get or create teacher role for school."""
        Role = _get_model('Role')
        
        # Try to get teacher role by system type
        try:
            return Role.objects.get(school=school, system_role_type='teacher')
        except Role.DoesNotExist:
            # Fallback: try to get any role named "Teacher"
            try:
                role = Role.objects.get(school=school, name='Teacher')
                # Update it to be a system role
                role.system_role_type = 'teacher'
                role.is_system_role = True
                role.save()
                return role
            except Role.DoesNotExist:
                # Fallback: create a basic teacher role
                base_name = "Teacher"
                role_name = base_name
                counter = 1
                while Role.objects.filter(school=school, name=role_name).exists():
                    role_name = f"{base_name} {counter}"
                    counter += 1
                    
                role = Role.objects.create(
                    name=role_name,
                    category='academic',
                    school=school,
                    system_role_type='teacher',
                    description='Teaching staff role',
                    permissions=['manage_attendance', 'manage_scores', 'view_reports', 'communicate'],
                    is_system_role=True,
                    can_manage_students=True,
                    can_manage_academics=True,
                    can_view_reports=True,
                    can_communicate=True,
                )
                return role
    
    @staticmethod
    def _create_staff_from_application(application, user, role):
        """Create staff record from teacher application."""
        Staff = _get_model('Staff')
        
        staff = Staff.objects.create(
            school=application.school,
            user=user,
            staff_id=StaffService.generate_staff_id(application.school),
            first_name=application.first_name,
            last_name=application.last_name,
            email=application.email,
            phone_number=application.phone_number,  # ✅ Already using shared field name
            position=application.position_applied,
            employment_type='probation',
            date_joined=timezone.now().date(),
            qualification=application.qualification,
            specialization=application.specialization,
            years_of_experience=application.years_of_experience,
            is_teaching_staff=True,
        )
        return staff
    
    @staticmethod
    def get_pending_invitations(school):
        """Get pending invitations for a school."""
        StaffInvitation = _get_model('StaffInvitation')
        
        return StaffInvitation.objects.filter(
            school=school, 
            status='pending',
            expires_at__gt=timezone.now()
        ).select_related('role', 'invited_by')
    
    @staticmethod
    def get_pending_applications(school):
        """Get pending applications for a school."""
        TeacherApplication = _get_model('TeacherApplication')
        
        return TeacherApplication.objects.filter(
            school=school,
            status='pending'
        ).select_related('applicant', 'position')
    
    @staticmethod
    def search_schools_for_application(query: str, user=None):
        """Search schools that are open for teacher applications."""
        School = _get_model('School', 'core')
        
        from django.db.models import Q, Count
        
        schools = School.objects.filter(
            is_active=True,
            openposition__is_active=True
        ).distinct()
        
        if query:
            schools = schools.filter(
                Q(name__icontains=query) |
                Q(address__icontains=query) |
                Q(subdomain__icontains=query)
            )
        
        # Annotate with open positions count
        schools = schools.annotate(
            open_positions_count=Count('openposition', filter=Q(openposition__is_active=True))
        ).filter(open_positions_count__gt=0)
        
        return schools
        
        
        @staticmethod
        def resend_invitation(invitation):
            """Resend an invitation email."""
            from .email_service import EmailService
            
            if invitation.status != 'pending':
                raise ValidationError("Cannot resend a non-pending invitation")
            
            if invitation.is_expired():
                raise ValidationError("Invitation has expired")
            
            # Send the invitation email
            EmailService.send_staff_invitation(
                invitation=invitation,
                resend=True
            )
            
            logger.info(f"Invitation resent to {invitation.email}")
            return invitation         