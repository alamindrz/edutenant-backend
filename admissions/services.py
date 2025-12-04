# billing/services.py
import requests
import logging
from django.conf import settings
from django.utils import timezone
from core.exceptions import PaymentProcessingError
from django.core.cache import cache
from django.db import transaction
from typing import Optional, Dict, Any
from users.models import Staff
from django.core.exceptions import ValidationError
from .models import ApplicationForm, Application, Admission
from students.models import Student, Parent
from billing.services import BillingService

# admissions/services.py
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.urls import reverse
from datetime import timedelta
import logging
import uuid


logger = logging.getLogger(__name__)




class AdmissionService:
    """Enhanced admission processing service."""
    
    @staticmethod
    @transaction.atomic
    def process_application_acceptance(application, reviewed_by):
        """Process application acceptance with full transaction safety."""
        try:
            # Create student if not exists
            if not application.student:
                student_data = {
                    'school': application.form.school,
                    'first_name': application.data.get('first_name', ''),
                    'last_name': application.data.get('last_name', ''),
                    'gender': application.data.get('gender', ''),
                    'date_of_birth': application.data.get('date_of_birth'),
                    'parent': application.parent,
                    'class_group': application.applied_class,
                    'admission_status': 'accepted',
                    'application_date': timezone.now()
                }
                application.student = Student.objects.create(**student_data)
            
            # Create admission offer
            admission = Admission.objects.create(
                application=application,
                student=application.student,
                offered_class=application.applied_class,
                requires_acceptance_fee=application.form.has_acceptance_fee
            )
            
            # Update application
            application.status = 'accepted'
            application.reviewed_at = timezone.now()
            application.assigned_to = reviewed_by
            application.save()
            
            # Invalidate cache
            cache.delete(f'school_{application.form.school.id}_admission_stats')
            
            return admission
            
        except Exception as e:
            logger.error(f"Failed to process application acceptance: {str(e)}")
            raise
    
    @staticmethod
    def get_admission_stats(school_id: int) -> Dict[str, Any]:
        """Get cached admission statistics."""
        cache_key = f'school_{school_id}_admission_stats'
        stats = cache.get(cache_key)
        
        if not stats:
            from .models import Application, Admission
            
            stats = {
                'total_applications': Application.objects.filter(form__school_id=school_id).count(),
                'pending_review': Application.objects.filter(
                    form__school_id=school_id, status='submitted'
                ).count(),
                'accepted': Application.objects.filter(
                    form__school_id=school_id, status='accepted'
                ).count(),
                'admitted': Admission.objects.filter(student__school_id=school_id).count(),
                'updated_at': timezone.now()
            }
            cache.set(cache_key, stats, 300)  # Cache for 5 minutes
        
        return stats




class PaystackService:
    """Enhanced Paystack service with split payments."""
    
    BASE_URL = "https://api.paystack.co"
    
    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        if not self.secret_key:
            logger.warning("Paystack secret key not configured")
    
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Paystack API."""
        try:
            url = f"{self.BASE_URL}{endpoint}"
            headers = {
                'Authorization': f'Bearer {self.secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.request(
                method, 
                url, 
                json=data, 
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API error: {str(e)}")
            raise PaymentProcessingError(
                "Payment service temporarily unavailable. Please try again.",
                user_friendly=True
            )
    
    def initialize_payment(self, invoice, parent_email, metadata=None):
        """Initialize payment for an invoice with split payments."""
        try:
            data = {
                'email': parent_email,
                'amount': int(invoice.total_amount * 100),  # Convert to kobo
                'reference': f"INV{invoice.id}{timezone.now().strftime('%Y%m%d%H%M%S')}",
                'metadata': {
                    'invoice_id': invoice.id,
                    'school_id': invoice.school.id,
                    'parent_id': invoice.parent.id,
                    'student_id': invoice.student.id,
                    'custom_fields': [
                        {
                            'display_name': "Invoice Number",
                            'variable_name': "invoice_number", 
                            'value': invoice.invoice_number
                        },
                        {
                            'display_name': "Student Name", 
                            'variable_name': "student_name",
                            'value': f"{invoice.student.first_name} {invoice.student.last_name}"
                        }
                    ]
                },
                'channels': ['card', 'bank', 'ussd', 'qr', 'mobile_money'],
                'subaccount': invoice.school.paystack_subaccount_id,
                'bearer': 'subaccount'  # School bears transaction fees
            }
            
            if metadata:
                data['metadata'].update(metadata)
            
            result = self._make_request('POST', '/transaction/initialize', data)
            
            if result.get('status'):
                return {
                    'authorization_url': result['data']['authorization_url'],
                    'access_code': result['data']['access_code'],
                    'reference': result['data']['reference']
                }
            else:
                raise PaymentProcessingError(
                    "Failed to initialize payment. Please try again.",
                    user_friendly=True
                )
                
        except Exception as e:
            logger.error(f"Failed to initialize payment for invoice {invoice.id}: {str(e)}")
            raise
    
    def verify_transaction(self, reference):
        """Verify Paystack transaction and process split payments."""
        try:
            result = self._make_request('GET', f'/transaction/verify/{reference}')
            
            if result.get('status') and result['data']['status'] == 'success':
                transaction_data = result['data']
                
                # Calculate split amounts
                total_amount = transaction_data['amount'] / 100  # Convert from kobo
                school_amount = total_amount - (transaction_data.get('fees', 0) / 100)
                
                return {
                    'status': 'success',
                    'amount': total_amount,
                    'school_amount': school_amount,
                    'fees': transaction_data.get('fees', 0) / 100,
                    'paid_at': transaction_data.get('paid_at'),
                    'metadata': transaction_data.get('metadata', {})
                }
            else:
                return {
                    'status': 'failed',
                    'message': result.get('message', 'Payment failed')
                }
                
        except Exception as e:
            logger.error(f"Failed to verify transaction {reference}: {str(e)}")
            return {'status': 'error', 'message': str(e)}
            
            


import logging
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ApplicationService:
    """
    Comprehensive service for managing student admission applications.
    Handles both external parent applications and staff child applications
    with configurable school policies for fees, discounts, and scholarships.
    """
    
    @staticmethod
    @transaction.atomic
    def submit_application(application_data, form_slug, user=None, request=None):
        """
        Submit a complete admission application with full validation and policy enforcement.
        
        Args:
            application_data: Dict containing parent and student information
            form_slug: Slug of the ApplicationForm
            user: Authenticated user making the submission (optional)
            request: HTTP request object for context (optional)
        
        Returns:
            Application: Created application instance
        
        Raises:
            ValidationError: If validation fails
            ApplicationForm.DoesNotExist: If form not found
        """
        logger.info(
            f"Application submission started - Form: {form_slug}, "
            f"User: {user.id if user else 'Anonymous'}"
        )
        
        try:
            # 1. Get and validate application form
            form = ApplicationService._get_and_validate_form(form_slug)
            
            # 2. Check school application policies
            ApplicationService._check_school_policies(form.school, user)
            
            # 3. Validate application data structure
            ApplicationService._validate_data_structure(application_data)
            
            # 4. Determine applicant type
            is_staff = ApplicationService._is_school_staff(user, form.school)
            
            # 5. Process application based on type
            if is_staff:
                logger.info(f"Processing staff child application - User: {user.id}")
                application = ApplicationService._process_staff_application(
                    form, application_data, user
                )
            else:
                logger.info(f"Processing external application - User: {user.id if user else 'Anonymous'}")
                application = ApplicationService._process_external_application(
                    form, application_data, user
                )
            
            # 6. Update form counter
            ApplicationService._update_form_counter(form)
            
            # 7. Handle application fee
            ApplicationService._handle_application_fee(application)
            
            # 8. Check scholarship eligibility
            scholarships = ApplicationService._check_scholarship_eligibility(
                application.student, application_data
            )
            if scholarships:
                application.scholarship_eligible = True
                application.potential_scholarships = scholarships
                application.save()
            
            logger.info(
                f"Application submitted successfully - "
                f"ID: {application.id}, Number: {application.application_number}"
            )
            
            return application
            
        except ValidationError as e:
            logger.warning(f"Application validation failed - Form: {form_slug}, Error: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Application submission failed - Form: {form_slug}, "
                f"Error: {str(e)}", exc_info=True
            )
            raise ValidationError("Failed to submit application. Please try again later.")
    
    @staticmethod
    def _get_and_validate_form(form_slug):
        """Get application form and validate it's active and open."""
        logger.debug(f"Validating application form: {form_slug}")
        
        form = get_object_or_404(ApplicationForm, slug=form_slug, status='active')
        
        now = timezone.now()
        
        if not form.is_open:
            raise ValidationError("This application form is no longer accepting submissions.")
        
        if form.open_date > now:
            raise ValidationError(
                f"This application form opens on {form.open_date.strftime('%B %d, %Y')}"
            )
        
        if form.close_date < now:
            raise ValidationError(
                f"This application form closed on {form.close_date.strftime('%B %d, %Y')}"
            )
        
        if form.max_applications and form.applications_so_far >= form.max_applications:
            raise ValidationError("This application form has reached its maximum number of submissions.")
        
        logger.debug(f"Form validation passed: {form_slug}")
        return form
    
    @staticmethod
    def _check_school_policies(school, user):
        """Check if school allows applications based on policies."""
        logger.debug(f"Checking school policies for school: {school.id}")
        
        if not school.application_form_enabled:
            raise ValidationError("This school is not currently accepting applications.")
        
        if not user or not user.is_authenticated:
            return
        
        is_staff = ApplicationService._is_school_staff(user, school)
        
        if is_staff and not school.allow_staff_applications:
            raise ValidationError("This school does not accept applications from staff members.")
        
        if not is_staff and not school.allow_external_applications:
            raise ValidationError("This school is not accepting external applications at this time.")
    
    @staticmethod
    def _is_school_staff(user, school):
        """Check if user is a staff member at the given school."""
        if not user or not user.is_authenticated:
            return False
        
        return Staff.objects.filter(
            user=user,
            school=school,
            is_active=True
        ).exists()
    
    @staticmethod
    def _validate_data_structure(application_data):
        """Validate the structure of application data."""
        logger.debug("Validating application data structure")
        
        if not isinstance(application_data, dict):
            raise ValidationError("Invalid application data format.")
        
        required_sections = ['parent_data', 'student_data']
        for section in required_sections:
            if section not in application_data:
                raise ValidationError(f"Missing required section: {section}")
            
            if not isinstance(application_data[section], dict):
                raise ValidationError(f"Invalid format for {section}")
        
        parent_data = application_data['parent_data']
        student_data = application_data['student_data']
        
        # Validate parent fields
        ApplicationService._validate_parent_data(parent_data)
        
        # Validate student fields
        ApplicationService._validate_student_data(student_data)
        
        logger.debug("Data structure validation passed")
    
    @staticmethod
    def _validate_parent_data(parent_data):
        """Validate parent data fields."""
        required_fields = ['first_name', 'last_name', 'email', 'phone']
        for field in required_fields:
            if not parent_data.get(field):
                raise ValidationError(f"Parent {field.replace('_', ' ')} is required")
        
        email = parent_data.get('email', '').strip()
        if '@' not in email or '.' not in email.split('@')[1]:
            raise ValidationError("Please provide a valid email address")
    
    @staticmethod
    def _validate_student_data(student_data):
        """Validate student data fields."""
        required_fields = ['first_name', 'last_name', 'gender', 'date_of_birth']
        for field in required_fields:
            if not student_data.get(field):
                raise ValidationError(f"Student {field.replace('_', ' ')} is required")
        
        dob = student_data.get('date_of_birth')
        if dob:
            try:
                dob_date = timezone.datetime.strptime(dob, '%Y-%m-%d').date()
                if dob_date > timezone.now().date():
                    raise ValidationError("Date of birth cannot be in the future")
            except ValueError:
                raise ValidationError("Invalid date format for date of birth. Use YYYY-MM-DD")
    
    @staticmethod
    def _process_staff_application(form, application_data, staff_user):
        """Process application for staff member's child."""
        logger.info(f"Processing staff application for user: {staff_user.id}")
        
        staff = get_object_or_404(
            Staff,
            user=staff_user,
            school=form.school,
            is_active=True
        )
        
        # Validate staff email
        if application_data['parent_data'].get('email', '').lower() != staff_user.email.lower():
            raise ValidationError("Staff must use their school-registered email address")
        
        # Get or create parent and student
        parent = ApplicationService._get_or_create_parent(
            application_data['parent_data'], form.school, staff_user, is_staff=True, staff=staff
        )
        
        student = ApplicationService._get_or_create_student(
            application_data['student_data'], parent, is_staff=True
        )
        
        # Validate class availability with staff priority
        applied_class = ApplicationService._validate_class_availability(
            application_data['student_data'].get('class_group_id'),
            form.school,
            is_staff=True
        )
        
        # Create application
        application = Application.objects.create(
            form=form,
            student=student,
            parent=parent,
            data=application_data,
            applied_class=applied_class,
            previous_school_info={
                'school': application_data['student_data'].get('previous_school', ''),
                'class': application_data['student_data'].get('previous_class', ''),
            },
            status='staff_review',
            priority='high',
            assigned_to=staff,
            review_notes=(
                f"Staff child application - Submitted by {staff_user.get_full_name()}\n"
                f"Staff Position: {staff.position}\n"
                f"Years of Service: {staff.years_of_service}"
            ),
            is_staff_child=True,
        )
        
        logger.info(f"Staff application created: {application.id}")
        return application
    
    @staticmethod
    def _process_external_application(form, application_data, user=None):
        """Process application for external (non-staff) parent."""
        logger.info(f"Processing external application for email: {application_data['parent_data'].get('email')}")
        
        # Check application limits
        email = application_data['parent_data']['email'].lower().strip()
        existing_apps = Application.objects.filter(
            form=form,
            parent__email=email,
            status__in=['submitted', 'under_review', 'waitlisted']
        ).count()
        
        if existing_apps >= 3:
            raise ValidationError(
                "You have reached the maximum number of applications allowed. "
                "Please contact the school administration if you need to submit additional applications."
            )
        
        # Get or create parent and student
        parent = ApplicationService._get_or_create_parent(
            application_data['parent_data'], form.school, user, is_staff=False
        )
        
        student = ApplicationService._get_or_create_student(
            application_data['student_data'], parent, is_staff=False
        )
        
        # Validate class availability
        applied_class = ApplicationService._validate_class_availability(
            application_data['student_data'].get('class_group_id'),
            form.school,
            is_staff=False
        )
        
        # Create application
        application = Application.objects.create(
            form=form,
            student=student,
            parent=parent,
            data=application_data,
            applied_class=applied_class,
            previous_school_info={
                'school': application_data['student_data'].get('previous_school', ''),
                'class': application_data['student_data'].get('previous_class', ''),
            },
            status='submitted',
            priority='normal',
            is_staff_child=False,
        )
        
        logger.info(f"External application created: {application.id}")
        return application
    
    @staticmethod
    def _get_or_create_parent(parent_data, school, user=None, is_staff=False, staff=None):
        """
        Get or create parent record for either staff or external applicants.
        
        Args:
            parent_data: Dict containing parent information
            school: School instance
            user: Associated user (optional)
            is_staff: Whether parent is a staff member
            staff: Staff instance (required if is_staff=True)
        
        Returns:
            Parent: Parent instance
        """
        email = parent_data['email'].lower().strip()
        logger.debug(f"Getting/creating parent for email: {email}, staff: {is_staff}")
        
        try:
            parent = Parent.objects.get(email=email, school=school)
            logger.debug(f"Found existing parent: {parent.id}")
            
            # Update parent information
            update_fields = []
            for field in ['first_name', 'last_name', 'phone', 'address', 'relationship']:
                if field in parent_data and parent_data[field]:
                    setattr(parent, field, parent_data[field])
                    update_fields.append(field)
            
            # Link user if provided
            if user and not parent.user:
                parent.user = user
                update_fields.append('user')
            
            # Handle staff flags
            if is_staff:
                if not parent.is_staff_child:
                    parent.is_staff_child = True
                    update_fields.append('is_staff_child')
                if staff and parent.staff_member != staff:
                    parent.staff_member = staff
                    update_fields.append('staff_member')
            else:
                if parent.is_staff_child:
                    parent.is_staff_child = False
                    parent.staff_member = None
                    update_fields.extend(['is_staff_child', 'staff_member'])
            
            if update_fields:
                parent.save(update_fields=update_fields)
                logger.debug(f"Updated parent fields: {update_fields}")
            
        except Parent.DoesNotExist:
            logger.debug(f"Creating new parent for email: {email}")
            
            if is_staff:
                # Create staff parent
                parent = Parent.objects.create(
                    school=school,
                    email=email,
                    first_name=staff.first_name if staff else parent_data.get('first_name', ''),
                    last_name=staff.last_name if staff else parent_data.get('last_name', ''),
                    phone=staff.phone_number if staff else parent_data.get('phone', ''),
                    address=parent_data.get('address', ''),
                    relationship=parent_data.get('relationship', 'Parent'),
                    user=user,
                    is_staff_child=True,
                    staff_member=staff,
                )
            else:
                # Create external parent
                parent = Parent.objects.create(
                    school=school,
                    email=email,
                    first_name=parent_data.get('first_name', ''),
                    last_name=parent_data.get('last_name', ''),
                    phone=parent_data.get('phone', ''),
                    address=parent_data.get('address', ''),
                    relationship=parent_data.get('relationship', 'Parent'),
                    user=user,
                    is_staff_child=False,
                )
            
            logger.debug(f"Created new parent: {parent.id}")
        
        return parent
    
    @staticmethod
    def _get_or_create_student(student_data, parent, is_staff=False):
        """
        Get or create student record, checking for duplicates.
        
        Args:
            student_data: Dict containing student information
            parent: Parent instance
            is_staff: Whether student is a staff child
        
        Returns:
            Student: Student instance
        
        Raises:
            ValidationError: If student is already enrolled
        """
        logger.debug(f"Getting/creating student for parent: {parent.id}, staff: {is_staff}")
        
        # Check for existing student
        existing_student = Student.objects.filter(
            school=parent.school,
            parent=parent,
            first_name__iexact=student_data['first_name'],
            last_name__iexact=student_data['last_name'],
            date_of_birth=student_data['date_of_birth']
        ).first()
        
        if existing_student:
            logger.debug(f"Found existing student: {existing_student.id}")
            
            # Check if already enrolled
            if existing_student.admission_status == 'enrolled':
                raise ValidationError(
                    f"Child {existing_student.full_name} is already enrolled. "
                    "Please contact administration for sibling enrollment."
                )
            
            # Update existing student
            existing_student.previous_school = student_data.get('previous_school', existing_student.previous_school)
            existing_student.previous_class = student_data.get('previous_class', existing_student.previous_class)
            if is_staff:
                existing_student.is_staff_child = True
            existing_student.save()
            
            return existing_student
        
        # Create new student
        admission_status = 'staff_review' if is_staff else 'applied'
        
        student = Student.objects.create(
            school=parent.school,
            first_name=student_data['first_name'],
            last_name=student_data['last_name'],
            gender=student_data['gender'],
            date_of_birth=student_data['date_of_birth'],
            parent=parent,
            previous_school=student_data.get('previous_school', ''),
            previous_class=student_data.get('previous_class', ''),
            admission_status=admission_status,
            application_date=timezone.now(),
            is_staff_child=is_staff,
        )
        
        logger.debug(f"Created new student: {student.id}")
        return student
    

    
    @staticmethod
    def _validate_class_availability(class_id, school, is_staff=False):
        """
        Validate class availability with staff priority.
        
        Args:
            class_id: ID of the class to apply for
            school: School instance
            is_staff: Whether applicant has staff priority
        
        Returns:
            ClassGroup: Class group instance if available
        
        Raises:
            ValidationError: If class is full or doesn't exist
        """
        if not class_id:
            return None
        
        logger.debug(f"Validating class availability: {class_id}, staff: {is_staff}")
        
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=school)
            
            if class_group.is_full:
                if is_staff and class_group.has_staff_reserved_seats():
                    logger.info(f"Using staff reserved seat in class: {class_group.name}")
                elif is_staff:
                    raise ValidationError(
                        f"No available staff seats in '{class_group.name}'. "
                        "Please select another class or contact administration."
                    )
                else:
                    raise ValidationError(f"Selected class '{class_group.name}' is full")
            
            logger.debug(f"Class validation passed: {class_group.name}")
            return class_group
            
        except ClassGroup.DoesNotExist:
            raise ValidationError("Selected class does not exist")
    
    @staticmethod
    def _update_form_counter(form):
        """Update application counter on the form."""
        form.applications_so_far += 1
        form.save(update_fields=['applications_so_far'])
        logger.debug(f"Updated form counter: {form.applications_so_far}")
    
    @staticmethod
    def _handle_application_fee(application):
        """
        Handle application fee with school policy enforcement.
        
        Args:
            application: Application instance
        """
        form = application.form
        
        # Check if fee is required
        if not form.school.application_fee_required or form.application_fee <= 0:
            logger.info(f"No application fee required for: {application.application_number}")
            return None
        
        # Check for staff child fee waiver
        if application.is_staff_child and form.school.staff_children_waive_application_fee:
            logger.info(f"Application fee waived for staff child: {application.application_number}")
            return None
        
        # Handle fee processing
        logger.info(f"Processing application fee for: {application.application_number}")
        # Fee processing logic would go here
        # This could involve creating a Payment record, integrating with payment gateway, etc.
    
    @staticmethod
    def _check_scholarship_eligibility(student, application_data):
        """
        Check if student is eligible for any scholarships.
        
        Args:
            student: Student instance
            application_data: Complete application data
        
        Returns:
            List: List of potential scholarships
        """
        logger.debug(f"Checking scholarship eligibility for student: {student.id}")
        
        scholarships = []
        
        # Scholarship eligibility logic would go here
        # This could check academic achievements, financial need, special talents, etc.
        
        if scholarships:
            logger.info(f"Student {student.id} eligible for {len(scholarships)} scholarships")
        
        return scholarships