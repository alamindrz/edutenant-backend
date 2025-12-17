# admissions/services.py
"""
CLEAN ApplicationService using shared architecture.
Removes ALL circular imports and ClassGroup references.
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

# FIXED: Use try/except for imports that might not exist
try:
    from shared.utils.field_mapping import FieldMapper as field_mapper
except ImportError:
    # Create minimal placeholder if not available
    class FieldMapper:
        @staticmethod
        def map_form_to_model(data, model_type):
            return data
    field_mapper = FieldMapper

try:
    from shared.utils.class_management import ClassManager as class_manager
except ImportError:
    # Create placeholder
    class_manager = None

try:
    from shared.services.payment.payment_core import PaymentCoreService as payment_core
except ImportError:
    # Create minimal placeholder
    class PaymentCoreService:
        @staticmethod
        def create_zero_amount_invoice(student, invoice_type, description):
            # Return minimal response
            return type('Invoice', (), {'id': 0})()
    payment_core = PaymentCoreService()

try:
    from shared.constants import StatusChoices
    STATUS_CHOICES_AVAILABLE = True
except ImportError:
    STATUS_CHOICES_AVAILABLE = False
    # Define minimal status choices
    class StatusChoices:
        PENDING = 'pending'
        SUBMITTED = 'submitted'
        UNDER_REVIEW = 'under_review'
        ACCEPTED = 'accepted'
        REJECTED = 'rejected'
        WAITLISTED = 'waitlisted'
        PAID = 'paid'

try:
    from shared.exceptions.payment import PaymentProcessingError
    PAYMENT_EXCEPTIONS_AVAILABLE = True
except ImportError:
    PAYMENT_EXCEPTIONS_AVAILABLE = False
    PaymentProcessingError = Exception

# LOCAL IMPORTS ONLY
from .models import ApplicationForm, Application, Admission
from students.models import Student, Parent
from users.models import Staff

logger = logging.getLogger(__name__)


class ApplicationService:
    """
    Comprehensive service for managing student admission applications.
    Uses shared services to avoid circular imports.
    """
    
    @staticmethod
    @transaction.atomic
    def submit_application(application_data, form_slug, user=None, request=None):
        """
        Submit a complete admission application with payment-first flow.
        
        Updated flow using shared architecture:
        1. Validate form and data using shared field_mapper
        2. Check if application fee is required
        3. If fee required: Use shared payment_core to create invoice
        4. If free/no fee: Create application directly
        """
        logger.info(
            f"Application submission started - Slug: {form_slug}, "
            f"User: {user.email if user and user.email else user.id if user else 'Anonymous'}"
        )
        
        try:
            # 1. Get and validate application form
            form = ApplicationService._get_and_validate_form(form_slug)
            
            # 2. Check school application policies
            ApplicationService._check_school_policies(form.school, user)
            
            # 3. Map form fields to model fields using shared field_mapper
            mapped_data = field_mapper.map_form_to_model(application_data, 'application')
            
            # 4. Check if application fee is required
            if not form.is_free and form.application_fee > 0:
                logger.info(f"Application fee required: ₦{form.application_fee:,.2f}")
                
                # Check if this is a post-payment completion
                if request and request.GET.get('payment_completed') == 'true':
                    reference = request.GET.get('reference')
                    if reference:
                        # Payment already completed, finish application
                        try:
                            from shared.services.payment.application_fee import ApplicationPaymentService
                            application = ApplicationPaymentService.complete_application_after_payment(reference)
                            return application
                        except ImportError:
                            logger.error("ApplicationPaymentService not available")
                            raise ValidationError("Payment service not available. Please contact support.")
                
                # Pre-payment flow: Create invoice and redirect to payment
                try:
                    from shared.services.payment.application_fee import ApplicationPaymentService
                    payment_data, invoice = ApplicationPaymentService.create_application_fee_invoice(
                        parent_data=mapped_data.get('parent_data', {}),
                        student_data=mapped_data.get('student_data', {}),
                        form=form,
                        user=user
                    )
                except ImportError:
                    logger.error("ApplicationPaymentService not available for invoice creation")
                    raise ValidationError("Payment processing is currently unavailable. Please try again later.")
                
                # Store application data in session for after payment
                if request:
                    request.session['pending_application'] = {
                        'form_slug': form_slug,
                        'application_data': application_data,
                        'invoice_id': invoice.id if hasattr(invoice, 'id') else None
                    }
                    request.session.modified = True
                
                # Return payment redirect info instead of application
                return {
                    'requires_payment': True,
                    'payment_data': payment_data if payment_data else {},
                    'invoice': invoice,
                    'message': 'Application fee payment required'
                }
            
            # 5. Free application - process directly
            is_staff = ApplicationService._is_school_staff(user, form.school)
            
            if is_staff:
                logger.info(f"Processing staff child application - User: {user.id}")
                application = ApplicationService._process_staff_application(
                    form, mapped_data, user
                )
            else:
                logger.info(f"Processing free external application - User: {user.id if user else 'Anonymous'}")
                application = ApplicationService._process_external_application(
                    form, mapped_data, user
                )
            
            # 6. Update form counter
            ApplicationService._update_form_counter(form)
            
            # 7. Check scholarship eligibility
            scholarships = ApplicationService._check_scholarship_eligibility(
                application.student, mapped_data
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
            logger.warning(f"Application validation failed: {e}")
            raise
        except PaymentProcessingError as e:
            logger.error(f"Payment processing error: {e}")
            raise ValidationError(str(e))
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
        
        # Check if school has application_form_enabled attribute
        if hasattr(school, 'application_form_enabled') and not school.application_form_enabled:
            raise ValidationError("This school is not currently accepting applications.")
        
        if not user or not user.is_authenticated:
            return
        
        is_staff = ApplicationService._is_school_staff(user, school)
        
        # Check staff applications
        if is_staff:
            if hasattr(school, 'allow_staff_applications') and not school.allow_staff_applications:
                raise ValidationError("This school does not accept applications from staff members.")
        
        # Check external applications
        if not is_staff:
            if hasattr(school, 'allow_external_applications') and not school.allow_external_applications:
                raise ValidationError("This school is not accepting external applications at this time.")
    
    @staticmethod
    def _is_school_staff(user, school):
        """Check if user is a staff member at the given school."""
        if not user or not user.is_authenticated:
            return False
        
        try:
            return Staff.objects.filter(
                user=user,
                school=school,
                is_active=True
            ).exists()
        except Exception:
            # If Staff model not available, assume not staff
            return False
    
    @staticmethod
    @transaction.atomic
    def _process_staff_application(form, mapped_data, staff_user):
        """Process application for staff member's child."""
        logger.info(f"Processing staff application for user: {staff_user.id}")
        
        staff = get_object_or_404(
            Staff,
            user=staff_user,
            school=form.school,
            is_active=True
        )
        
        # Validate staff email
        parent_email = mapped_data.get('parent_data', {}).get('email', '').lower()
        if parent_email != staff_user.email.lower():
            raise ValidationError("Staff must use their school-registered email address")
        
        # Get or create parent and student
        parent = ApplicationService._get_or_create_parent(
            mapped_data.get('parent_data', {}), form.school, staff_user, is_staff=True, staff=staff
        )
        
        student = ApplicationService._get_or_create_student(
            mapped_data.get('student_data', {}), parent, is_staff=True
        )
        
        # Validate class availability with staff priority using shared manager
        class_id = mapped_data.get('student_data', {}).get('current_class_id')
        if class_id and class_manager:
            is_available, message, class_instance = class_manager.validate_class_availability(
                class_id, form.school, is_staff=True
            )
            if not is_available:
                raise ValidationError(message)
        else:
            class_instance = None
        
        # Determine status
        status = StatusChoices.UNDER_REVIEW if STATUS_CHOICES_AVAILABLE else 'under_review'
        
        # Create application
        application = Application.objects.create(
            form=form,
            student=student,
            parent=parent,
            data=mapped_data,
            applied_class=class_instance,
            previous_school_info={
                'school': mapped_data.get('student_data', {}).get('previous_school', ''),
                'class': mapped_data.get('student_data', {}).get('previous_class', ''),
            },
            status=status,
            priority='high',
            assigned_to=staff,
            review_notes=(
                f"Staff child application - Submitted by {staff_user.get_full_name()}\n"
                f"Staff Position: {staff.position if hasattr(staff, 'position') else 'Not specified'}\n"
                f"Years of Service: {staff.years_of_service if hasattr(staff, 'years_of_service') else 'Not specified'}"
            ),
            is_staff_child=True,
        )
        
        # Handle zero-fee application for staff
        if form.application_fee > 0 and hasattr(form.school, 'staff_children_waive_application_fee') and form.school.staff_children_waive_application_fee:
            try:
                invoice = payment_core.create_zero_amount_invoice(
                    student=student,
                    invoice_type='application_fee',
                    description=f'Staff waiver - Application fee for {student.full_name}'
                )
                application.application_fee_paid = True
                application.application_fee_invoice = invoice
                application.save()
            except Exception as e:
                logger.warning(f"Failed to create zero amount invoice for staff: {e}")
        
        logger.info(f"Staff application created: {application.id}")
        return application
    
    @staticmethod
    @transaction.atomic
    def _process_external_application(form, mapped_data, user=None):
        """Process application for external (non-staff) parent."""
        parent_email = mapped_data.get('parent_data', {}).get('email', '').lower().strip()
        logger.info(f"Processing external application for email: {parent_email}")
        
        # Check application limits
        existing_apps = Application.objects.filter(
            form=form,
            parent__email=parent_email,
            status__in=['submitted', 'under_review', 'waitlisted']
        ).count()
        
        if existing_apps >= 3:
            raise ValidationError(
                "You have reached the maximum number of applications allowed. "
                "Please contact the school administration if you need to submit additional applications."
            )
        
        # Get or create parent and student
        parent = ApplicationService._get_or_create_parent(
            mapped_data.get('parent_data', {}), form.school, user, is_staff=False
        )
        
        student = ApplicationService._get_or_create_student(
            mapped_data.get('student_data', {}), parent, is_staff=False
        )
        
        # Validate class availability using shared manager
        class_id = mapped_data.get('student_data', {}).get('current_class_id')
        if class_id and class_manager:
            is_available, message, class_instance = class_manager.validate_class_availability(
                class_id, form.school, is_staff=False
            )
            if not is_available:
                raise ValidationError(message)
        else:
            class_instance = None
        
        # Determine status
        status = StatusChoices.SUBMITTED if STATUS_CHOICES_AVAILABLE else 'submitted'
        
        # Create application
        application = Application.objects.create(
            form=form,
            student=student,
            parent=parent,
            data=mapped_data,
            applied_class=class_instance,
            previous_school_info={
                'school': mapped_data.get('student_data', {}).get('previous_school', ''),
                'class': mapped_data.get('student_data', {}).get('previous_class', ''),
            },
            status=status,
            priority='normal',
            is_staff_child=False,
        )
        
        logger.info(f"External application created: {application.id}")
        return application
    
    @staticmethod
    def _get_or_create_parent(parent_data, school, user=None, is_staff=False, staff=None):
        """
        Get or create parent record for either staff or external applicants.
        Uses shared field_mapper for consistent field names.
        """
        email = parent_data.get('email', '').lower().strip()
        if not email:
            raise ValidationError("Parent email is required")
        
        logger.debug(f"Getting/creating parent for email: {email}, staff: {is_staff}")
        
        try:
            parent = Parent.objects.get(email=email, school=school)
            logger.debug(f"Found existing parent: {parent.id}")
            
            # Update parent information
            update_fields = []
            
            # Use parent_data which is already mapped by field_mapper
            if 'first_name' in parent_data and parent_data['first_name']:
                parent.first_name = parent_data['first_name']
                update_fields.append('first_name')
            
            if 'last_name' in parent_data and parent_data['last_name']:
                parent.last_name = parent_data['last_name']
                update_fields.append('last_name')
            
            if 'phone_number' in parent_data and parent_data['phone_number']:
                parent.phone_number = parent_data['phone_number']
                update_fields.append('phone_number')
            
            if 'address' in parent_data and parent_data['address']:
                parent.address = parent_data['address']
                update_fields.append('address')
            
            if 'relationship' in parent_data and parent_data['relationship']:
                parent.relationship = parent_data['relationship']
                update_fields.append('relationship')
            
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
            
            # Prepare parent creation data
            parent_kwargs = {
                'school': school,
                'email': email,
                'first_name': parent_data.get('first_name', ''),
                'last_name': parent_data.get('last_name', ''),
                'phone_number': parent_data.get('phone_number', ''),
                'address': parent_data.get('address', ''),
                'relationship': parent_data.get('relationship', 'Parent'),
                'user': user,
            }
            
            if is_staff:
                # Staff parent specific fields
                if staff:
                    parent_kwargs.update({
                        'first_name': staff.first_name if hasattr(staff, 'first_name') else parent_data.get('first_name', ''),
                        'last_name': staff.last_name if hasattr(staff, 'last_name') else parent_data.get('last_name', ''),
                        'phone_number': staff.phone_number if hasattr(staff, 'phone_number') else parent_data.get('phone_number', ''),
                    })
                parent_kwargs.update({
                    'is_staff_child': True,
                    'staff_member': staff,
                })
            else:
                # External parent specific fields
                parent_kwargs.update({
                    'is_staff_child': False,
                    'staff_member': None,
                })
            
            parent = Parent.objects.create(**parent_kwargs)
            logger.debug(f"Created new parent: {parent.id}")
        
        return parent
    
    @staticmethod
    def _get_or_create_student(student_data, parent, is_staff=False):
        """
        Get or create student record, checking for duplicates.
        """
        logger.debug(f"Getting/creating student for parent: {parent.id}, staff: {is_staff}")
        
        # Check for required fields
        required_fields = ['first_name', 'last_name', 'date_of_birth']
        for field in required_fields:
            if field not in student_data or not student_data[field]:
                raise ValidationError(f"Student {field.replace('_', ' ')} is required")
        
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
            update_fields = []
            if 'previous_school' in student_data and student_data['previous_school']:
                existing_student.previous_school = student_data['previous_school']
                update_fields.append('previous_school')
            if 'previous_class' in student_data and student_data['previous_class']:
                existing_student.previous_class = student_data['previous_class']
                update_fields.append('previous_class')
            
            if is_staff and not existing_student.is_staff_child:
                existing_student.is_staff_child = True
                update_fields.append('is_staff_child')
            
            if update_fields:
                existing_student.save(update_fields=update_fields)
            
            return existing_student
        
        # Determine admission status
        if STATUS_CHOICES_AVAILABLE:
            admission_status = StatusChoices.UNDER_REVIEW if is_staff else StatusChoices.APPLIED
        else:
            admission_status = 'under_review' if is_staff else 'applied'
        
        # Create new student
        student = Student.objects.create(
            school=parent.school,
            first_name=student_data['first_name'],
            last_name=student_data['last_name'],
            gender=student_data.get('gender', ''),
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
    def _update_form_counter(form):
        """Update application counter on the form."""
        form.applications_so_far = form.applications.count()
        form.save(update_fields=['applications_so_far'])
        logger.debug(f"Updated form counter: {form.applications_so_far}")
    
    @staticmethod
    def _check_scholarship_eligibility(student, application_data):
        """
        Check if student is eligible for any scholarships.
        """
        logger.debug(f"Checking scholarship eligibility for student: {student.id}")
        
        scholarships = []
        
        # Scholarship eligibility logic would go here
        # This could check academic achievements, financial need, special talents, etc.
        
        if scholarships:
            logger.info(f"Student {student.id} eligible for {len(scholarships)} scholarships")
        
        return scholarships
    
    @staticmethod
    def complete_application_after_payment(payment_reference, invoice_id=None):
        """
        Complete application creation after successful payment.
        This is called by payment webhook or success callback.
        """
        logger.info(f"Completing application after payment: {payment_reference}")
        
        try:
            # Get invoice
            try:
                from billing.models import Invoice
            except ImportError:
                logger.error("Billing models not available")
                raise ValidationError("Billing system not available")
            
            if invoice_id:
                invoice = Invoice.objects.get(id=invoice_id)
            else:
                # Find invoice by reference
                invoice = Invoice.objects.filter(
                    metadata__reference=payment_reference
                ).first()
            
            if not invoice:
                raise ValidationError(f"No invoice found for payment reference: {payment_reference}")
            
            # Get stored application data
            metadata = invoice.metadata or {}
            application_data = metadata.get('application_data', {})
            form_slug = metadata.get('form_slug')
            
            if not application_data or not form_slug:
                raise ValidationError("Missing application data in invoice metadata")
            
            # Process the application
            application = ApplicationService.submit_application(
                application_data=application_data,
                form_slug=form_slug,
                user=None,  # User will be determined from parent email
                request=None
            )
            
            # Link invoice to application
            application.application_fee_paid = True
            application.application_fee_invoice = invoice
            application.save()
            
            logger.info(f"Application completed after payment: {application.application_number}")
            return application
            
        except Exception as e:
            logger.error(f"Failed to complete application after payment: {str(e)}")
            raise