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

logger = logging.getLogger(__name__)

# ============ SHARED SERVICE IMPORTS WITH FALLBACKS ============

# Field Mapper
try:
    from shared.utils.field_mapping import FieldMapper as field_mapper
    FIELD_MAPPER_AVAILABLE = True
except ImportError:
    FIELD_MAPPER_AVAILABLE = False
    # Create minimal placeholder
    class FieldMapper:
        @staticmethod
        def map_form_to_model(data, model_type):
            return data
    field_mapper = FieldMapper()
    logger.warning("Shared FieldMapper not available, using fallback")

# Class Manager
try:
    from shared.utils.class_management import ClassManager as class_manager
    CLASS_MANAGER_AVAILABLE = True
except ImportError:
    CLASS_MANAGER_AVAILABLE = False
    class_manager = None
    logger.warning("Shared ClassManager not available")

# Payment Services
try:
    from shared.services.payment.application_fee import ApplicationPaymentService
    APPLICATION_PAYMENT_SERVICE_AVAILABLE = True
except ImportError:
    APPLICATION_PAYMENT_SERVICE_AVAILABLE = False
    ApplicationPaymentService = None
    logger.warning("Shared ApplicationPaymentService not available")

try:
    from shared.services.payment.payment_core import PaymentCoreService as payment_core
    PAYMENT_CORE_AVAILABLE = True
except ImportError:
    PAYMENT_CORE_AVAILABLE = False
    # Create minimal placeholder
    class PaymentCoreService:
        @staticmethod
        def create_zero_amount_invoice(student, invoice_type, description):
            # Return minimal response
            return type('Invoice', (), {
                'id': 0,
                'amount': 0,
                'invoice_number': 'WAIVER-0000',
                'metadata': {}
            })()

        @staticmethod
        def mark_paid(invoice, payment_method, reference, notes):
            # Mock implementation
            return True
    payment_core = PaymentCoreService()
    logger.warning("Shared PaymentCoreService not available, using fallback")

# Shared Constants
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
    logger.warning("Shared StatusChoices not available, using fallback")

# Payment Exceptions
try:
    from shared.exceptions.payment import PaymentProcessingError
    PAYMENT_EXCEPTIONS_AVAILABLE = True
except ImportError:
    PAYMENT_EXCEPTIONS_AVAILABLE = False
    PaymentProcessingError = Exception
    logger.warning("Shared PaymentProcessingError not available, using fallback")

# ============ LOCAL IMPORTS ============
from .models import ApplicationForm, Application, Admission
from students.models import Student, Parent
from users.models import Staff


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
            mapped_data = application_data
            if FIELD_MAPPER_AVAILABLE:
                mapped_data = field_mapper.map_form_to_model(application_data, 'application')

            # 4. Check if application fee is required
            if not form.is_free and form.application_fee > 0:
                logger.info(f"Application fee required: ₦{form.application_fee:,.2f}")

                # Check if this is a post-payment completion
                if request and request.GET.get('payment_completed') == 'true':
                    reference = request.GET.get('reference')
                    if reference and APPLICATION_PAYMENT_SERVICE_AVAILABLE:
                        # Payment already completed, finish application
                        application = ApplicationPaymentService.complete_application_after_payment(reference)
                        return application

                # Pre-payment flow: Create invoice and redirect to payment
                if APPLICATION_PAYMENT_SERVICE_AVAILABLE:
                    payment_data, invoice = ApplicationPaymentService.create_application_fee_invoice(
                        parent_data=mapped_data.get('parent_data', {}),
                        student_data=mapped_data.get('student_data', {}),
                        form=form,
                        user=user
                    )
                else:
                    # Fallback: create invoice locally
                    logger.warning("Using fallback for application fee invoice creation")
                    invoice = ApplicationService._create_local_invoice(form, mapped_data, user)
                    payment_data = {
                        'authorization_url': '#',
                        'reference': f'LOCAL-{invoice.id}',
                        'amount': form.application_fee
                    }

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
                    'form': form,
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

            # 8. Send notification
            ApplicationService._send_application_submitted_notification(application, user)

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
    def _create_local_invoice(form, mapped_data, user):
        """Fallback method to create invoice locally when shared service is unavailable."""
        # This is a simplified version - in production, you'd want to use your actual Invoice model
        class LocalInvoice:
            id = 0
            amount = form.application_fee
            invoice_number = f"LOCAL-{int(timezone.now().timestamp())}"
            metadata = {
                'form_slug': form.slug,
                'application_data': mapped_data,
                'user_id': user.id if user else None,
                'created_at': timezone.now().isoformat()
            }

            def __str__(self):
                return self.invoice_number

        return LocalInvoice()

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
        except Exception as e:
            logger.warning(f"Error checking staff status: {e}")
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
        class_id = mapped_data.get('student_data', {}).get('class')
        class_instance = None

        if class_id and CLASS_MANAGER_AVAILABLE:
            is_available, message, class_instance = class_manager.validate_class_availability(
                class_id, form.school, is_staff=True
            )
            if not is_available:
                raise ValidationError(message)
        elif class_id:
            # Fallback: try to get class directly
            try:
                from core.models import Class
                class_instance = Class.objects.get(id=class_id, school=form.school)
            except:
                pass

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
                if PAYMENT_CORE_AVAILABLE:
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
        class_id = mapped_data.get('student_data', {}).get('class')
        class_instance = None

        if class_id and CLASS_MANAGER_AVAILABLE:
            is_available, message, class_instance = class_manager.validate_class_availability(
                class_id, form.school, is_staff=False
            )
            if not is_available:
                raise ValidationError(message)
        elif class_id:
            # Fallback: try to get class directly
            try:
                from core.models import Class
                class_instance = Class.objects.get(id=class_id, school=form.school)
            except:
                pass

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


        try:
            parent = Parent.objects.get(email=email, school=school)
            logger.debug(f"Found existing parent: {parent.id}")

            # Update parent information
            update_fields = []

            # Map field names based on what's available in parent_data
            field_mapping = {
                'first_name': 'first_name',
                'last_name': 'last_name',
                'phone': 'phone_number',
                'phone_number': 'phone_number',
                'address': 'address',
                'relationship': 'relationship'
            }

            for form_field, model_field in field_mapping.items():
                if form_field in parent_data and parent_data[form_field]:
                    setattr(parent, model_field, parent_data[form_field])
                    if model_field not in update_fields:
                        update_fields.append(model_field)

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
                'phone_number': parent_data.get('phone_number', parent_data.get('phone', '')),
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
            admission_status = StatusChoices.UNDER_REVIEW if is_staff else StatusChoices.UNDER_REVIEW
        else:
            admission_status = 'under_review' if is_staff else 'under_review'

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

        # Example criteria:
        # 1. Academic excellence
        if application_data.get('student_data', {}).get('previous_school_gpa', 0) >= 3.5:
            scholarships.append({
                'type': 'academic_excellence',
                'amount': '50%',
                'description': 'Academic Excellence Scholarship'
            })

        # 2. Sports achievement
        if application_data.get('student_data', {}).get('sports_achievements'):
            scholarships.append({
                'type': 'sports_scholarship',
                'amount': '25%',
                'description': 'Sports Achievement Scholarship'
            })

        if scholarships:
            logger.info(f"Student {student.id} eligible for {len(scholarships)} scholarships")

        return scholarships

    @staticmethod
    def _send_application_submitted_notification(application, user):
        """Send notification about application submission."""
        logger.debug(f"Sending notification for application: {application.id}")

        try:
            # This would integrate with email/SMS notification system
            notification_data = {
                'application_number': application.application_number,
                'student_name': application.student_full_name,
                'parent_email': application.parent.email,
                'submitted_at': application.submitted_at.isoformat(),
                'status': application.status,
                'is_staff_child': application.is_staff_child,
            }

            # Log notification for now - in production, send actual notification
            logger.info(f"Application notification prepared: {notification_data}")

        except Exception as e:
            logger.warning(f"Failed to send application notification: {e}")

    @staticmethod
    def complete_application_after_payment(payment_reference, invoice_id=None):
        """
        Complete application creation after successful payment.
        This is called by payment webhook or success callback.
        """
        logger.info(f"Completing application after payment: {payment_reference}")

        try:
            # Try to use shared service first
            if APPLICATION_PAYMENT_SERVICE_AVAILABLE:
                return ApplicationPaymentService.complete_application_after_payment(payment_reference)

            # Fallback implementation
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


class AdmissionService:
    """Service for managing admission offers and enrollment."""

    @staticmethod
    @transaction.atomic
    def process_application_acceptance(application, staff):
        """
        Process acceptance of an application and create admission offer.
        """
        logger.info(f"Processing acceptance for application: {application.id}")

        try:
            # Validate application is accepted
            if application.status != 'accepted':
                raise ValidationError("Application must be accepted before creating admission")

            # Validate staff permissions
            if not staff.is_active or staff.school != application.form.school:
                raise ValidationError("Staff member is not authorized to create admissions")

            # Create admission
            admission = Admission.objects.create(
                application=application,
                student=application.student,
                offered_class=application.applied_class or application.form.available_classes.first(),
                requires_acceptance_fee=application.form.has_acceptance_fee,
                acceptance_fee=application.form.acceptance_fee if application.form.has_acceptance_fee else 0,
                created_by=staff,
                conditions=[
                    "Submit original birth certificate",
                    "Submit medical report",
                    "Submit transfer certificate (if applicable)",
                    "Complete enrollment within 30 days"
                ]
            )

            # Update student status
            application.student.admission_status = 'admitted'
            application.student.save(update_fields=['admission_status'])

            # Send admission letter
            admission.send_admission_letter(method='email')

            logger.info(f"Admission created: {admission.admission_number}")
            return admission

        except Exception as e:
            logger.error(f"Failed to create admission: {str(e)}")
            raise

    @staticmethod
    def complete_enrollment(admission, parent_notes=''):
        """
        Complete enrollment process for an admitted student.
        """
        logger.info(f"Completing enrollment for admission: {admission.id}")

        try:
            # Validate admission can be enrolled
            if not admission.can_complete_enrollment():
                raise ValidationError("Admission does not meet all enrollment requirements")

            # Update admission
            admission.enrollment_completed = True
            admission.enrollment_completed_at = timezone.now()
            if parent_notes:
                admission.acceptance_notes = parent_notes
            admission.save()

            # Update student
            admission.student.current_class = admission.offered_class
            admission.student.admission_status = 'enrolled'
            admission.student.enrollment_date = timezone.now()
            admission.student.save()

            # Send enrollment confirmation
            AdmissionService._send_enrollment_confirmation(admission)

            logger.info(f"Enrollment completed for student: {admission.student.id}")
            return admission

        except Exception as e:
            logger.error(f"Failed to complete enrollment: {str(e)}")
            raise

    @staticmethod
    def _send_enrollment_confirmation(admission):
        """Send enrollment confirmation notification."""
        try:
            notification_data = {
                'admission_number': admission.admission_number,
                'student_name': admission.student.full_name,
                'class_name': admission.offered_class.name,
                'enrollment_date': admission.enrollment_completed_at.isoformat(),
                'parent_email': admission.student.parent.email,
            }

            logger.info(f"Enrollment confirmation prepared: {notification_data}")

        except Exception as e:
            logger.warning(f"Failed to send enrollment confirmation: {e}")

    @staticmethod
    def get_admission_stats(school):
        """Get admission statistics for a school."""
        stats = {
            'total_applications': Application.objects.filter(form__school=school).count(),
            'pending_review': Application.objects.filter(form__school=school, status='submitted').count(),
            'under_review': Application.objects.filter(form__school=school, status='under_review').count(),
            'accepted': Application.objects.filter(form__school=school, status='accepted').count(),
            'admitted': Admission.objects.filter(student__school=school).count(),
            'enrolled': Admission.objects.filter(
                student__school=school,
                enrollment_completed=True
            ).count(),
        }

        # Calculate conversion rates
        if stats['total_applications'] > 0:
            stats['acceptance_rate'] = round((stats['accepted'] / stats['total_applications']) * 100, 1)
            stats['enrollment_rate'] = round((stats['enrolled'] / stats['accepted']) * 100, 1) if stats['accepted'] > 0 else 0
        else:
            stats['acceptance_rate'] = 0
            stats['enrollment_rate'] = 0

        return stats
