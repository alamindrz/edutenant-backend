# users/services.py 
import logging
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from core.exceptions import SchoolOnboardingError, ValidationError
from .models import Profile, StaffInvitation, Role, TeacherApplication, Staff


logger = logging.getLogger(__name__)
User = get_user_model()


class PaystackService:
    """Mock Paystack service for development - will be replaced with real implementation."""
    
    @staticmethod
    def create_subaccount(school):
        """Create Paystack subaccount for school."""
        try:
            # Validate required fields
            if not school.bank_code or not school.account_number:
                raise ValidationError("Bank code and account number are required for subaccount creation")
            
            # Mock implementation - replace with actual Paystack API call
            subaccount_id = f"SUBACC_{school.id}_{int(timezone.now().timestamp())}"
            logger.info(f"Created Paystack subaccount: {subaccount_id} for school: {school.name}")
            
            return subaccount_id
            
        except Exception as e:
            logger.error(f"Paystack subaccount creation failed for school {school.id}: {str(e)}")
            raise PaymentProcessingError("Failed to create payment subaccount") from e
    
    @staticmethod
    def initialize_subscription(school, billing_period='monthly'):
        """Initialize subscription payment."""
        try:
            # Mock implementation - replace with actual Paystack API call
            return {
                'authorization_url': f'https://paystack.com/pay/sub_{school.id}',
                'access_code': f'access_{school.id}',
                'reference': f"SUB_REF_{school.id}_{int(timezone.now().timestamp())}"
            }
        except Exception as e:
            logger.error(f"Subscription initialization failed for school {school.id}: {str(e)}")
            raise PaymentProcessingError("Failed to initialize subscription") from e


class EmailService:
    """Service for handling email communications."""
    
    @staticmethod
    def send_welcome_email(school, admin_user):
        """Send welcome email to school admin."""
        try:
            subject = f"Welcome to Edusuite - {school.name} is Ready!"
            
            context = {
                'school': school,
                'admin_user': admin_user,
                'login_url': 'http://localhost:8000/accounts/login/',  # Update in production
                'dashboard_url': 'http://localhost:8000/dashboard/',
                'support_email': 'support@edusuite.com',
            }
            
            html_message = render_to_string('emails/welcome_school.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject,
                plain_message,
                'noreply@edusuite.com',
                [admin_user.email],
                html_message=html_message,
                fail_silently=False  # Raise exception on failure
            )
            
            logger.info(f"Welcome email sent successfully to {admin_user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {admin_user.email}: {str(e)}")
            # Don't raise - email failure shouldn't break onboarding
            # In production, you might want to queue this for retry


class ValidationService:
    """Service for data validation."""
    
    @staticmethod
    def validate_subdomain(subdomain):
        """Validate subdomain format and availability."""
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
        from .models import School
        if School.objects.filter(subdomain=subdomain).exists():
            return False, SchoolOnboardingService.get_subdomain_suggestions(subdomain)
        
        return True, []
    
    @staticmethod
    def validate_onboarding_data(data):
        """Validate school onboarding data."""
        required_fields = ['school_name', 'school_type', 'contact_email', 'admin_email', 'admin_password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}", user_friendly=True)
        
  
        
        # Password strength (basic check)
        if len(data['admin_password']) < 8:
            raise ValidationError("Password must be at least 8 characters long", user_friendly=True)


class SchoolOnboardingService:
    """Complete service for automating school onboarding and configuration.
    Handles the entire school setup process including validation, creation, and configuration.
    """

    @staticmethod
    @transaction.atomic
    def create_school_from_template(onboarding_data):
        logger.info("Starting school onboarding process", extra={'school_name': onboarding_data.get('school_name')})
        try:
            # Step 1: Validate input data
            ValidationService.validate_onboarding_data(onboarding_data)

            # Step 2: Check if admin user already exists
            admin_email = onboarding_data['admin_email']
            if User.objects.filter(email=admin_email).exists():
                raise SchoolOnboardingError(
                    f"User with email {admin_email} already exists.",
                    user_friendly=True
                )

            # Step 3: Create school record
            school = SchoolOnboardingService._create_school_record(onboarding_data)

            # Apply configuration template
            SchoolOnboardingService._apply_configuration_template(school, onboarding_data['school_type'])

            # Verify principal role was created
            from .models import Role
            if not Role.objects.filter(school=school, system_role_type='principal').exists():
                logger.error("Principal role was not created during template application")
                raise SchoolOnboardingError(
                    "System configuration failed. Please try again or contact support.",
                    user_friendly=True
                )

            # Step 4: Create admin user
            admin_user = SchoolOnboardingService._create_school_admin(school, onboarding_data)

            # Verify profile was created
            if not Profile.objects.filter(user=admin_user, school=school).exists():
                raise SchoolOnboardingError(
                    "Failed to create user profile during school setup.",
                    user_friendly=True
                )

            try:
                from core.services import ClassManagementService
                ClassManagementService.create_classes_from_template(
                    school=school,
                    school_type=onboarding_data['school_type']
                )
                logger.info(f"Classes created for school {school.name}")
            except Exception as e:
                logger.warning(f"Class creation failed but continuing: {e}")  # Non-critical setup

            SchoolOnboardingService._setup_payment_integration(school)
            EmailService.send_welcome_email(school, admin_user)

            logger.info("School onboarding completed successfully", extra={'school_id': school.id})
            return school
        except Exception as e:
            logger.error("School onboarding failed", extra={'error': str(e)}, exc_info=True)
            raise

    @staticmethod
    def _create_school_record(onboarding_data):
        """Create the school database record."""
        from .models import School
        try:
            subdomain = onboarding_data.get('subdomain', '').strip()
            subdomain_status = 'none'  # Default to no subdomain

            # Determine subdomain status
            if subdomain:
                subdomain_status = 'active'  # Auto-activate for now
            school = School.objects.create(
                name=onboarding_data['school_name'],
                subdomain=subdomain or None,
                school_type=onboarding_data['school_type'],
                contact_email=onboarding_data['contact_email'],
                phone_number=onboarding_data.get('phone_number'),
                address=onboarding_data.get('address'),
                bank_code=onboarding_data.get('bank_code'),
                account_number=onboarding_data.get('account_number'),
                account_name=onboarding_data.get('account_name'),
                subdomain_status=subdomain_status,
                subdomain_expires_at=timezone.now() + timedelta(days=30) if subdomain else None,
                onboarding_completed=True
            )
            return school
        except Exception as e:
            logger.error("Failed to create school record", extra={'school_name': onboarding_data['school_name'], 'error': str(e)})
            raise

    @staticmethod
    def _setup_payment_integration(school):
        """Set up payment integration for school."""
        try:
            subaccount_id = PaystackService.create_subaccount(school)
            school.paystack_subaccount_id = subaccount_id
            school.save()
            logger.info("Payment integration setup completed", extra={'school_id': school.id})
        except Exception as e:
            logger.warning("Payment integration setup failed - school can still operate", extra={'school_id': school.id, 'error': str(e)})  # Don't raise - payment setup failure shouldn't break onboarding

    @staticmethod
    def _apply_configuration_template(school, school_type):
        """Apply pre-configured template based on school type."""
        from .models import Role
        try:
            template_config = SchoolOnboardingService._get_template_config(school_type)
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
            logger.info("School template applied successfully", extra={'school_id': school.id, 'school_type': school_type})
        except Exception as e:
            logger.error("Failed to apply school template", extra={'school_id': school.id, 'school_type': school_type, 'error': str(e)})
            raise

    @staticmethod
    def _create_school_admin(school, onboarding_data):
        """Create school admin user and principal role."""
        from .models import Role, Profile
        try:
            # Check we're not creating duplicates
            if User.objects.filter(email=onboarding_data['admin_email']).exists():
                raise SchoolOnboardingError(
                    f"User {onboarding_data['admin_email']} already exists",
                    user_friendly=True
                )

            # Create admin user
            admin_user = User.objects.create_user(
                email=onboarding_data['admin_email'],
                username=onboarding_data['admin_email'],
                password=onboarding_data['admin_password'],
                first_name=onboarding_data.get('admin_first_name', 'School'),
                last_name=onboarding_data.get('admin_last_name', 'Admin'),
                phone_number=onboarding_data.get('admin_phone')
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
                phone_number=onboarding_data.get('admin_phone')
            )

            # Set current school
            admin_user.current_school = school
            admin_user.save()

            # Verify everything worked
            if not hasattr(admin_user, 'current_school') or not admin_user.current_school:
                raise SchoolOnboardingError("Failed to set current school for admin user")

            logger.info("School admin created successfully", extra={'school_id': school.id, 'admin_email': admin_user.email})
            return admin_user
        except Exception as e:
            logger.error("Failed to create school admin", extra={'school_id': school.id, 'error': str(e)})
            # If we created the user but failed later, delete the user to avoid orphans
            if 'admin_user' in locals() and admin_user.id:
                admin_user.delete()
            raise

    @staticmethod
    def _cleanup_failed_onboarding(local_vars):
        """Clean up partially created data from failed onboarding."""
        try:
            if 'school' in local_vars and local_vars['school']:
                local_vars['school'].delete()
                logger.info("Cleaned up partially created school due to onboarding failure")
        except Exception as e:
            logger.error("Failed to clean up onboarding data", extra={'error': str(e)})


    @staticmethod
    def _get_template_config(school_type):
        """Get template configuration for school type."""
        templates = {
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
                    {
                        'name': 'Administrative Staff',
                        'category': 'administration',
                        'system_role_type': 'admin_staff',
                        'description': 'Administrative staff with limited permissions',
                        'permissions': ['manage_students', 'view_reports'],
                        'can_manage_roles': False,
                        'can_manage_staff': False,
                        'can_manage_students': True,
                        'can_manage_academics': False,
                        'can_manage_finances': False,
                        'can_view_reports': True,
                        'can_communicate': True,
                    }
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
                    {
                        'name': 'Head Teacher',
                        'category': 'academic',
                        'system_role_type': 'head_teacher',
                        'description': 'Senior teacher with additional permissions',
                        'permissions': ['manage_attendance', 'manage_scores', 'view_reports', 'communicate', 'manage_academics'],
                        'can_manage_roles': False,
                        'can_manage_staff': False,
                        'can_manage_students': True,
                        'can_manage_academics': True,
                        'can_manage_finances': False,
                        'can_view_reports': True,
                        'can_communicate': True,
                    }
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
                    {
                        'name': 'Department Head',
                        'category': 'academic',
                        'system_role_type': 'department_head',
                        'description': 'Department head with supervisory permissions',
                        'permissions': ['manage_attendance', 'manage_scores', 'view_reports', 'communicate', 'manage_academics'],
                        'can_manage_roles': False,
                        'can_manage_staff': True,
                        'can_manage_students': True,
                        'can_manage_academics': True,
                        'can_manage_finances': False,
                        'can_view_reports': True,
                        'can_communicate': True,
                    }
                ]
            },
            'combined': {
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
                    }
                ]
            },
            'full': {
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
                    }
                ]
            }
        }
        return templates.get(school_type, templates['primary'])

    @staticmethod
    def is_subdomain_available(subdomain):
        """Check if subdomain is available."""
        from .models import School  # Local import to avoid circular dependency
        if not subdomain or subdomain.strip() == '':
            # Empty subdomain is always "available" (means no subdomain)
            return True
        return not School.objects.filter(subdomain=subdomain.strip()).exists()

    @staticmethod
    def get_subdomain_suggestions(requested_subdomain):
        """Get alternative subdomain suggestions when requested is unavailable."""
        from .models import School
        suggestions = []
        base = requested_subdomain.strip()
        if not base:
            return suggestions

        # Try different variations
        variations = [
            # ... (variations omitted for brevity)
        ]
        for variation in variations:
            if not School.objects.filter(subdomain=variation).exists():
                suggestions.append(variation)
            if len(suggestions) >= 3:
                break
        return suggestions
  


class RoleManagementService:
    """Service for role management operations."""
    
    @staticmethod
    def create_custom_role(school, role_data):
        """Create custom role with permissions."""
        from .models import Role
        
        try:
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

class StaffService:
    """Unified service for all staff-related operations."""
    
    # ===== STAFF ID GENERATION =====
    @staticmethod
    def generate_staff_id(school):
        """Generate unique staff ID for school."""
        from .models import Staff
        
        last_staff = Staff.objects.filter(school=school).order_by('-id').first()
        if last_staff and last_staff.staff_id:
            try:
                # Extract numeric part and increment
                import re
                match = re.search(r'(\d+)$', last_staff.staff_id)
                if match:
                    next_num = int(match.group(1)) + 1
                    return f"STAFF{next_num:03d}"
            except (ValueError, AttributeError):
                pass
        
        # Default format
        return f"STAFF001"
    
    # ===== TEACHER INVITATIONS =====
    @staticmethod
    def invite_teacher(school, invited_by, email, role_id, message=""):
        """Invite a teacher to join the school."""
        from django.utils.crypto import get_random_string
        from datetime import timedelta
        
        # Validate inputs
        if not email or not role_id:
            raise ValidationError("Email and role are required")
        
        # Check if user already exists and has access
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if Profile.objects.filter(user=existing_user, school=school).exists():
                raise ValidationError(f"{email} already has access to {school.name}")
        
        # Get role
        try:
            role = Role.objects.get(id=role_id, school=school)
        except Role.DoesNotExist:
            raise ValidationError("Invalid role selected")
        
        # Create invitation
        token = get_random_string(50)
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
        invitation.send_invitation_email()
        
        logger.info(f"Teacher invitation sent to {email} for school {school.name}")
        return invitation
    
    @staticmethod
    def accept_invitation(token, user_data):
        """Accept invitation and create teacher account."""
        try:
            invitation = StaffInvitation.objects.get(token=token, status='pending')
            
            if not invitation.is_valid():
                raise ValidationError("Invitation has expired or is no longer valid")
            
            with transaction.atomic():
                # Get or create user
                user, created = User.objects.get_or_create(
                    email=invitation.email,
                    defaults={
                        'username': invitation.email,
                        'first_name': user_data.get('first_name', ''),
                        'last_name': user_data.get('last_name', ''),
                        'phone_number': user_data.get('phone_number', ''),
                    }
                )
                
                if created:
                    user.set_password(user_data['password'])
                    user.save()
                
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
                        'position': invitation.role.name,
                        'employment_type': 'full_time'
                    }
                )
                
                logger.info(f"Teacher onboarding completed: {user.email} for school {invitation.school.name}")
                return user
                
        except StaffInvitation.DoesNotExist:
            raise ValidationError("Invalid invitation token")
    
    @staticmethod
    def get_pending_invitations(school):
        """Get pending invitations for a school."""
        return StaffInvitation.objects.filter(
            school=school, 
            status='pending',
            expires_at__gt=timezone.now()
        ).select_related('role', 'invited_by')
    
    # ===== TEACHER APPLICATIONS =====
    @staticmethod
    def submit_application(application_data, school, user=None):
        """Submit a new teacher application."""
        try:
            # Validate application data
            if not application_data.get('email') or not application_data.get('first_name') or not application_data.get('last_name'):
                raise ValidationError("Email, first name, and last name are required")
            
            # Check for duplicate pending applications
            existing_application = TeacherApplication.objects.filter(
                school=school,
                email=application_data['email'],
                status='pending'
            ).exists()
            
            if existing_application:
                raise ValidationError("You already have a pending application for this school")
            
            # Get position if specified
            position = None
            if application_data.get('position_id'):
                try:
                    position = OpenPosition.objects.get(
                        id=application_data['position_id'],
                        school=school,
                        is_active=True
                    )
                except OpenPosition.DoesNotExist:
                    raise ValidationError("Selected position is no longer available")
            
            # Create application
            application = TeacherApplication.objects.create(
                school=school,
                position=position,
                applicant=user,
                email=application_data['email'],
                first_name=application_data['first_name'],
                last_name=application_data['last_name'],
                phone_number=application_data.get('phone_number', ''),
                application_type=application_data.get('application_type', 'experienced'),
                position_applied=application_data.get('position_applied', 'Teacher'),
                years_of_experience=application_data.get('years_of_experience', 0),
                qualification=application_data.get('qualification', ''),
                specialization=application_data.get('specialization', ''),
                cover_letter=application_data.get('cover_letter', ''),
                resume=application_data.get('resume'),
                certificates=application_data.get('certificates'),
            )
            
            # Send notification to school admins
            StaffService._notify_school_admins(application)
            
            logger.info(f"Teacher application submitted: {application.full_name} to {school.name}")
            return application
            
        except Exception as e:
            logger.error(f"Failed to submit teacher application: {str(e)}")
            raise
    
    @staticmethod
    def approve_application(application, approved_by):
        """Approve a teacher application and create staff record."""
        try:
            with transaction.atomic():
                # Get or create user account
                user, created = User.objects.get_or_create(
                    email=application.email,
                    defaults={
                        'username': application.email,
                        'first_name': application.first_name,
                        'last_name': application.last_name,
                        'phone_number': application.phone_number,
                    }
                )
                
                if created:
                    # Generate temporary password
                    temp_password = User.objects.make_random_password()
                    user.set_password(temp_password)
                    user.save()
                
                # Get teacher role - with robust fallback logic
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
                application.status = 'approved'
                application.status_changed_by = approved_by
                application.status_changed_at = timezone.now()
                application.applicant = user
                application.save()
                
                logger.info(f"Teacher application approved and staff created: {staff.full_name}")
                return staff
                
        except Exception as e:
            logger.error(f"Failed to approve teacher application: {str(e)}")
            raise
    
    @staticmethod
    def _get_teacher_role(school):
        """Get or create teacher role for school."""
        # Try to get teacher role by system type
        try:
            return Role.objects.get(school=school, system_role_type='teacher')
        except Role.DoesNotExist:
            # Fallback 1: try to get any role named "Teacher"
            try:
                role = Role.objects.get(school=school, name='Teacher')
                # Update it to be a system role
                role.system_role_type = 'teacher'
                role.is_system_role = True
                role.save()
                return role
            except Role.DoesNotExist:
                # Fallback 2: try to get any academic role
                role = Role.objects.filter(school=school, category='academic').first()
                
                # Fallback 3: create a basic teacher role
                if not role:
                    # Generate unique name if needed
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
        staff = Staff.objects.create(
            school=application.school,
            user=user,
            staff_id=StaffService.generate_staff_id(application.school),
            first_name=application.first_name,
            last_name=application.last_name,
            email=application.email,
            phone_number=application.phone_number,
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
    def get_pending_applications(school):
        """Get pending applications for a school."""
        return TeacherApplication.objects.filter(
            school=school,
            status='pending'
        ).select_related('applicant', 'position')
    
    @staticmethod
    def search_schools_for_application(query, user=None):
        """Search schools that are open for teacher applications."""
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
        from django.db.models import Count
        schools = schools.annotate(
            open_positions_count=Count('openposition', filter=Q(openposition__is_active=True))
        ).filter(open_positions_count__gt=0)
        
        return schools
    
    @staticmethod
    def _notify_school_admins(application):
        """Notify school admins about new application."""
        try:
            admin_profiles = Profile.objects.filter(
                school=application.school,
                role__can_manage_staff=True
            ).select_related('user')
            
            # Email implementation would go here
            for profile in admin_profiles:
                pass
                
        except Exception as e:
            logger.error(f"Failed to send admin notification: {str(e)}")
    
    # ===== STAFF MANAGEMENT =====
    @staticmethod
    def create_staff_user(staff):
        """Create user account for staff member."""
        try:
            if staff.user:
                logger.warning(f"Staff {staff.id} already has a user account")
                return staff.user
            
            user = User.objects.create_user(
                email=staff.email,
                username=staff.email,
                password=User.objects.make_random_password(),
                first_name=staff.first_name,
                last_name=staff.last_name,
                phone_number=staff.phone_number
            )
            
            staff.user = user
            staff.save()
            
            logger.info(f"User account created successfully for staff {staff.id}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to create user account for staff {staff.id}: {str(e)}")
            raise

class PaymentProcessingError(SchoolOnboardingError):
    """Payment-related errors."""
    def __init__(self, message=None, user_friendly=False, details=None):
        super().__init__(message or "Payment processing failed", user_friendly, details)

