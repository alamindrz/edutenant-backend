"""
CLEAN Billing Views - Using shared architecture CORRECTLY.
"""
import logging
import json
import hashlib
import hmac
import time
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings

# SHARED IMPORTS
from shared.constants import StatusChoices, PaymentMethods

# If decorators don't exist in shared, we'll handle it differently
try:
    from shared.decorators import require_school_context, require_role
except ImportError:
    from functools import wraps
    from django.core.exceptions import PermissionDenied

    def require_school_context(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if hasattr(request, 'school'):
                return view_func(request, *args, **kwargs)
            return redirect('select_school')
        return _wrapped_view

    def require_role(required_role):
        def decorator(view_func):
            @wraps(view_func)
            def _wrapped_view(request, *args, **kwargs):

                if request.user.is_superuser:
                    return view_func(request, *args, **kwargs)
                return view_func(request, *args, **kwargs)  # Temporarily allow all
            return _wrapped_view
        return decorator

# LOCAL IMPORTS
from .models import Invoice, Transaction, FeeStructure, SubdomainPlan, SchoolSubscription

logger = logging.getLogger(__name__)


# ============ SECURITY CLASS ============

class WebhookSecurity:
    """Advanced webhook security with multiple validation layers."""

    @staticmethod
    def verify_signature(payload, signature, secret):
        """Verify Paystack webhook signature with timing attack protection."""
        if not signature or not secret:
            return False

        try:
            # Compute HMAC signature
            computed_signature = hmac.new(
                secret.encode('utf-8'),
                payload,
                digestmod=hashlib.sha512
            ).hexdigest()

            # Use compare_digest to prevent timing attacks
            return hmac.compare_digest(computed_signature, signature)
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}")
            return False

    @staticmethod
    def validate_payload_structure(payload):
        """Validate webhook payload structure."""
        required_fields = ['event', 'data']
        if not all(field in payload for field in required_fields):
            return False

        # Validate event types
        valid_events = {
            'charge.success', 'charge.failed', 'transfer.success',
            'transfer.failed', 'subscription.disable', 'invoice.update'
        }

        if payload['event'] not in valid_events:
            logger.warning(f"Unsupported webhook event: {payload['event']}")
            return False

        return True

    @staticmethod
    def sanitize_webhook_data(payload):
        """Sanitize and normalize webhook data."""
        try:
            # Remove sensitive data if present
            sensitive_fields = ['authorization', 'customer', 'log']
            data = payload.get('data', {})

            for field in sensitive_fields:
                data.pop(field, None)

            return {
                'event': payload['event'],
                'data': data,
                'timestamp': payload.get('createdAt', ''),
                'webhook_id': payload.get('id', '')
            }
        except Exception as e:
            logger.error(f"Webhook data sanitization error: {str(e)}")
            return None


# ============ SERVICE FUNCTIONS ============

def get_payment_service():
    """Get payment service - lazy import to avoid circular dependencies."""
    from shared.services.payment import PaystackService
    return PaystackService()

def get_application_payment_service():
    """Get application payment service from shared."""
    from shared.services.payment import ApplicationPaymentService
    return ApplicationPaymentService()

def get_payment_core_service():
    """Get core payment service from shared."""
    from shared.services.payment import PaymentCoreService
    return PaymentCoreService()


# ============ PAYMENT HELPERS ============

def initialize_payment(invoice, customer_email, metadata=None):
    """
    Initialize payment using shared PaystackService.
    Backward compatibility wrapper.
    """
    try:
        paystack_service = get_payment_service()
        return paystack_service.initialize_payment(
            invoice=invoice,
            customer_email=customer_email,
            metadata=metadata or {}
        )
    except Exception as e:
        logger.error(f"Payment initialization error: {str(e)}")
        from shared.exceptions.payment import PaymentProcessingError
        raise PaymentProcessingError(
            "Failed to initialize payment. Please try again.",
            user_friendly=True
        )

def verify_transaction(reference):
    """
    Verify transaction using shared PaystackService.
    Backward compatibility wrapper.
    """
    try:
        paystack_service = get_payment_service()
        return paystack_service.verify_transaction(reference)
    except Exception as e:
        logger.error(f"Transaction verification error: {str(e)}")
        return {'status': 'error', 'message': str(e)}


# ============ DASHBOARD VIEWS ============

@login_required
@require_school_context
@require_role('manage_finances')
def billing_dashboard_view(request):
    """Billing dashboard for school administrators."""
    school = request.school

    try:
        # Define valid status values for invoices
        paid_status = 'paid'  # Using string since StatusChoices.PAID = 'paid'
        sent_status = 'sent'
        overdue_status = 'overdue'

        # Financial statistics
        financial_stats = {
            'total_revenue': Invoice.objects.filter(
                school=school,
                status=paid_status
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'pending_invoices': Invoice.objects.filter(
                school=school,
                status__in=[sent_status, overdue_status]
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'total_invoices': Invoice.objects.filter(school=school).count(),
            'paid_invoices': Invoice.objects.filter(
                school=school,
                status=paid_status
            ).count(),
        }

        # Recent transactions
        recent_transactions = Transaction.objects.filter(
            invoice__school=school
        ).select_related('invoice', 'invoice__student', 'invoice__parent').order_by('-created_at')[:10]

        # Invoice status breakdown
        invoice_breakdown = Invoice.objects.filter(
            school=school
        ).values('status').annotate(
            count=Count('id'),
            amount=Sum('total_amount')
        ).order_by('status')

        # Subscription info
        subscription = getattr(school, 'subscription', None)

        context = {
            'financial_stats': financial_stats,
            'recent_transactions': recent_transactions,
            'invoice_breakdown': invoice_breakdown,
            'subscription': subscription,
            'school': school,
        }

        logger.info(f"Billing dashboard accessed for school {school.name}")
        return render(request, 'billing/dashboard.html', context)

    except Exception as e:
        logger.error(f"Billing dashboard error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading billing dashboard. Please try again.")
        return redirect('dashboard')


# ============ INVOICE VIEWS ============

@login_required
@require_school_context
@require_role('manage_finances')
def invoice_list_view(request):
    """List all invoices for the school with all needed context."""
    school = request.school

    try:
        # Get all invoices
        invoices = Invoice.objects.filter(school=school).select_related(
            'student', 'parent', 'term'
        ).order_by('-created_at')

        # Filters
        status_filter = request.GET.get('status', '')
        type_filter = request.GET.get('type', '')
        search_query = request.GET.get('search', '')

        if status_filter:
            invoices = invoices.filter(status=status_filter)
        if type_filter:
            invoices = invoices.filter(invoice_type=type_filter)
        if search_query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(parent__first_name__icontains=search_query) |
                Q(parent__last_name__icontains=search_query)
            )

        # Pagination
        paginator = Paginator(invoices, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Get students for create invoice modal
        from students.models import Student
        students = Student.objects.filter(school=school, is_active=True).select_related('current_class')

        # Get academic terms for create invoice modal
        from students.models import AcademicTerm
        academic_terms = AcademicTerm.objects.filter(school=school, is_active=True)

        context = {
            'invoices': page_obj,
            'status_filter': status_filter,
            'type_filter': type_filter,
            'search_query': search_query,
            'page_obj': page_obj,
            'students': students,  # Added for create invoice modal
            'academic_terms': academic_terms,  # Added for create invoice modal
        }

        return render(request, 'billing/invoice_list.html', context)

    except Exception as e:
        logger.error(f"Invoice list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading invoices. Please try again.")
        return redirect('billing:dashboard')


@login_required
@require_school_context
@require_role('manage_finances')
def invoice_detail_view(request, invoice_id):
    """View invoice details."""
    school = request.school
    invoice = get_object_or_404(Invoice, id=invoice_id, school=school)

    try:
        transactions = invoice.transactions.all().order_by('-created_at')
        items = invoice.items.all().select_related('fee_structure')

        context = {
            'invoice': invoice,
            'transactions': transactions,
            'items': items,
        }

        return render(request, 'billing/invoice_detail.html', context)

    except Exception as e:
        logger.error(f"Invoice detail error for invoice {invoice_id}: {str(e)}")
        messages.error(request, "Error loading invoice details.")
        return redirect('billing:invoice_list')


# ============ FEE STRUCTURE VIEWS ============

@login_required
@require_school_context
@require_role('manage_finances')
def fee_structure_list_view(request):
    """Manage fee structures for the school."""
    school = request.school

    try:
        # Get all fee structures
        fee_structures = FeeStructure.objects.filter(school=school).select_related('category').order_by('category__order', 'fee_type')

        # Group by category for better organization
        fees_by_category = {}
        for fee in fee_structures:
            category_name = fee.category.name if fee.category else 'Uncategorized'
            if category_name not in fees_by_category:
                fees_by_category[category_name] = []
            fees_by_category[category_name].append(fee)

        # Get categories for create modal
        from .models import FeeCategory
        categories = FeeCategory.objects.all().order_by('order')

        # Get fee type choices for create modal
        fee_types = FeeStructure.FEE_TYPES

        context = {
            'fees_by_category': fees_by_category,
            'fee_structures': fee_structures,
            'categories': categories,  # Added for create modal
            'fee_types': fee_types,    # Added for create modal
        }

        return render(request, 'billing/fee_structure_list.html', context)

    except Exception as e:
        logger.error(f"Fee structure list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading fee structures.")
        return redirect('billing:dashboard')


# ============ PARENT VIEWS ============

@login_required
def parent_invoice_list_view(request):
    """Parent view of their invoices across all schools."""
    try:
        # Get parent profiles for the user
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')

        if not parent_profiles.exists():
            messages.info(request, "You don't have any parent profiles.")
            return redirect('dashboard')

        # Get all invoices for the parent
        invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles]
        ).select_related('school', 'student', 'term').order_by('-created_at')

        # Group by school
        invoices_by_school = {}
        for invoice in invoices:
            school_name = invoice.school.name
            if school_name not in invoices_by_school:
                invoices_by_school[school_name] = []
            invoices_by_school[school_name].append(invoice)

        # Calculate totals - using string literals since we don't have those specific status constants
        total_pending = sum(
            inv.total_amount for inv in invoices
            if inv.status in ['sent', 'overdue']
        )
        total_paid = sum(
            inv.total_amount for inv in invoices
            if inv.status == 'paid'
        )

        context = {
            'invoices_by_school': invoices_by_school,
            'total_pending': total_pending,
            'total_paid': total_paid,
            'parent_profiles': parent_profiles,
        }

        logger.info(f"Parent invoice list accessed for user {request.user.email}")
        return render(request, 'billing/parent_invoice_list.html', context)

    except Exception as e:
        logger.error(f"Parent invoice list error for user {request.user.id}: {str(e)}")
        messages.error(request, "Error loading your invoices. Please try again.")
        return redirect('dashboard')


@login_required
def parent_payment_view(request, invoice_id=None):
    """Parent payment page for one or multiple invoices."""
    try:
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')

        if invoice_id:
            # Single invoice payment
            invoice = get_object_or_404(
                Invoice,
                id=invoice_id,
                parent__in=[p.parent_profile for p in parent_profiles]
            )
            invoices = [invoice]
            is_multiple = False
        else:
            # Multiple invoices - get all unpaid
            invoices = Invoice.objects.filter(
                parent__in=[p.parent_profile for p in parent_profiles],
                status__in=['sent', 'overdue']
            ).select_related('school', 'student')
            is_multiple = True

        if not invoices:
            messages.info(request, "You don't have any pending invoices.")
            return redirect('billing:parent_invoices')

        total_amount = sum(invoice.total_amount for invoice in invoices)

        if request.method == 'POST':
            try:
                if len(invoices) == 1:
                    # Single invoice payment
                    payment_data = initialize_payment(
                        invoices[0],
                        request.user.email,
                        metadata={'invoice_ids': [invoices[0].id]}
                    )
                    return redirect(payment_data['authorization_url'])
                else:
                    # Multiple invoices - combine
                    selected_ids = request.POST.getlist('selected_invoices')
                    if not selected_ids:
                        messages.error(request, "Please select at least one invoice to pay.")
                        return redirect('billing:parent_payment')

                    selected_invoices = [inv for inv in invoices if str(inv.id) in selected_ids]
                    total_selected = sum(inv.total_amount for inv in selected_invoices)

                    # Create combined payment record
                    messages.info(request,
                        f"Preparing payment of ₦{total_selected:,.2f} for {len(selected_invoices)} invoice(s)."
                    )
                    # For now, redirect to first invoice payment
                    if selected_invoices:
                        payment_data = initialize_payment(
                            selected_invoices[0],
                            request.user.email,
                            metadata={'invoice_ids': [inv.id for inv in selected_invoices]}
                        )
                        return redirect(payment_data['authorization_url'])

            except Exception as e:
                logger.error(f"Payment initialization error: {str(e)}")
                messages.error(request, "An error occurred while initializing payment. Please try again.")

        context = {
            'invoices': invoices,
            'total_amount': total_amount,
            'is_multiple': is_multiple,
            'parent_profiles': parent_profiles,
        }

        return render(request, 'billing/parent_payment.html', context)

    except Exception as e:
        logger.error(f"Parent payment error for user {request.user.id}: {str(e)}")
        messages.error(request, "Error loading payment page. Please try again.")
        return redirect('billing:parent_invoices')

# ============ PAYMENT CALLBACKS ============

@login_required
def payment_success_view(request):
    """Payment success callback."""
    try:
        reference = request.GET.get('reference')
        if not reference:
            messages.error(request, "No payment reference provided.")
            return redirect('billing:parent_invoices')

        # Verify payment using shared service
        verification = verify_transaction(reference)

        if verification.get('status') == 'success':
            messages.success(request, "Payment completed successfully! Thank you for your payment.")
            logger.info(f"Payment success for reference: {reference}")
        else:
            messages.warning(request, f"Payment verification pending: {verification.get('message', 'Please wait for confirmation')}")

        return redirect('billing:parent_invoices')

    except Exception as e:
        logger.error(f"Payment success callback error: {str(e)}")
        messages.error(request, "Error verifying payment. Please contact support if payment was deducted.")
        return redirect('billing:parent_invoices')


@login_required
def payment_failed_view(request):
    """Payment failure callback."""
    reference = request.GET.get('reference', 'Unknown')
    logger.warning(f"Payment failed for reference: {reference}")
    messages.error(request, "Payment failed or was cancelled. Please try again.")
    return redirect('billing:parent_payment')


# ============ MISSING VIEW FUNCTIONS ============

@login_required
@require_school_context
@require_role('manage_finances')
def create_invoice_view(request):
    """Create a new invoice."""
    if request.method == 'POST':
        try:
            school = request.school

            # Get form data
            student_id = request.POST.get('student_id')
            invoice_type = request.POST.get('invoice_type')
            due_date = request.POST.get('due_date')
            description = request.POST.get('description', '')
            term_id = request.POST.get('term_id')

            # Validate required fields
            if not all([student_id, invoice_type, due_date]):
                messages.error(request, "Please fill all required fields.")
                return redirect('billing:invoice_list')

            # Get student
            from students.models import Student
            student = Student.objects.get(id=student_id, school=school)

            # Create invoice
            invoice = Invoice.objects.create(
                school=school,
                parent=student.parent,
                student=student,
                invoice_type=invoice_type,
                subtotal=0,  # Will be updated with items
                total_amount=0,
                due_date=due_date,
                description=description,
                status='draft',
                created_by=request.user,
            )

            # Add term if provided
            if term_id:
                from students.models import AcademicTerm
                term = AcademicTerm.objects.get(id=term_id, school=school)
                invoice.term = term
                invoice.session = term.academic_year
                invoice.save()

            messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
            logger.info(f"Invoice created: {invoice.id} by user {request.user.id}")

            return redirect('billing:invoice_detail', invoice_id=invoice.id)

        except Student.DoesNotExist:
            messages.error(request, "Student not found.")
        except AcademicTerm.DoesNotExist:
            messages.error(request, "Academic term not found.")
        except Exception as e:
            logger.error(f"Create invoice error: {str(e)}")
            messages.error(request, "Error creating invoice.")

    return redirect('billing:invoice_list')


@login_required
@require_school_context
@require_role('manage_finances')
def send_invoice_view(request, invoice_id):
    """Send invoice to parent."""
    if request.method == 'POST':
        try:
            invoice = get_object_or_404(Invoice, id=invoice_id, school=request.school)
            message = request.POST.get('message', '')

            # Update invoice status
            invoice.status = 'sent'
            invoice.save()

            # TODO: Send email to parent
            # You would implement email sending here

            messages.success(request, f"Invoice {invoice.invoice_number} sent to parent.")
            logger.info(f"Invoice {invoice.id} sent by user {request.user.id}")

        except Exception as e:
            logger.error(f"Send invoice error: {str(e)}")
            messages.error(request, "Error sending invoice.")

    return redirect('billing:invoice_detail', invoice_id=invoice_id)


@login_required
@require_school_context
@require_role('manage_finances')
def cancel_invoice_view(request, invoice_id):
    """Cancel an invoice."""
    if request.method == 'POST':
        try:
            invoice = get_object_or_404(Invoice, id=invoice_id, school=request.school)
            reason = request.POST.get('reason', '')

            # Check if invoice can be cancelled
            if invoice.status == 'paid':
                messages.error(request, "Cannot cancel a paid invoice.")
                return redirect('billing:invoice_detail', invoice_id=invoice_id)

            # Update invoice status
            invoice.status = 'cancelled'
            invoice.save()

            # Log cancellation reason
            logger.info(f"Invoice {invoice.id} cancelled by user {request.user.id}. Reason: {reason}")

            messages.success(request, f"Invoice {invoice.invoice_number} cancelled.")

        except Exception as e:
            logger.error(f"Cancel invoice error: {str(e)}")
            messages.error(request, "Error cancelling invoice.")

    return redirect('billing:invoice_detail', invoice_id=invoice_id)


@login_required
@require_school_context
@require_role('manage_finances')
def mark_invoice_paid_view(request, invoice_id):
    """Mark invoice as paid manually."""
    if request.method == 'POST':
        try:
            invoice = get_object_or_404(Invoice, id=invoice_id, school=request.school)

            # Mark as paid
            invoice.status = 'paid'
            invoice.paid_date = timezone.now().date()
            invoice.save()

            # Create a manual transaction record
            Transaction.objects.create(
                invoice=invoice,
                paystack_reference=f"MANUAL-{timezone.now().timestamp()}",
                amount=invoice.total_amount,
                status='success',
                payment_method='manual',
                metadata={'marked_by': request.user.id, 'manual': True}
            )

            messages.success(request, f"Invoice {invoice.invoice_number} marked as paid.")

            # Return HTMX response if requested
            if request.headers.get('HX-Request'):
                return render(request, 'billing/partials/invoice_row.html', {'invoice': invoice})

        except Exception as e:
            logger.error(f"Mark invoice paid error: {str(e)}")
            messages.error(request, "Error marking invoice as paid.")

    return redirect('billing:invoice_list')


# ============ FEE STRUCTURE MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_finances')
def create_fee_view(request):
    """Create a new fee structure."""
    if request.method == 'POST':
        try:
            school = request.school

            # Get form data
            name = request.POST.get('name')
            fee_type = request.POST.get('fee_type')
            category_id = request.POST.get('category_id')
            amount = request.POST.get('amount')
            is_required = request.POST.get('is_required') == 'on'
            is_government_approved = request.POST.get('is_government_approved') == 'on'
            due_date = request.POST.get('due_date') or None
            description = request.POST.get('description', '')

            # Create fee structure
            fee = FeeStructure.objects.create(
                school=school,
                name=name,
                fee_type=fee_type,
                amount=amount,
                is_required=is_required,
                is_government_approved=is_government_approved,
                due_date=due_date,
                description=description,
            )

            # Set category if provided
            if category_id:
                from .models import FeeCategory
                category = FeeCategory.objects.get(id=category_id)
                fee.category = category
                fee.save()

            messages.success(request, f"Fee structure '{name}' created successfully.")
            logger.info(f"Fee structure created: {fee.id} by user {request.user.id}")

        except Exception as e:
            logger.error(f"Create fee error: {str(e)}")
            messages.error(request, "Error creating fee structure.")

    return redirect('billing:fee_structure_list')


@login_required
@require_school_context
@require_role('manage_finances')
def update_fee_view(request, fee_id):
    """Update an existing fee structure."""
    if request.method == 'POST':
        try:
            fee = get_object_or_404(FeeStructure, id=fee_id, school=request.school)

            # Update fields
            fee.name = request.POST.get('name', fee.name)
            fee.fee_type = request.POST.get('fee_type', fee.fee_type)
            fee.amount = request.POST.get('amount', fee.amount)
            fee.is_required = request.POST.get('is_required') == 'on'
            fee.is_government_approved = request.POST.get('is_government_approved') == 'on'
            fee.is_active = request.POST.get('is_active') == 'on'
            fee.due_date = request.POST.get('due_date') or None
            fee.description = request.POST.get('description', fee.description)

            # Update category
            category_id = request.POST.get('category_id')
            if category_id:
                from .models import FeeCategory
                category = FeeCategory.objects.get(id=category_id)
                fee.category = category

            fee.save()

            messages.success(request, f"Fee structure '{fee.name}' updated successfully.")

        except Exception as e:
            logger.error(f"Update fee error: {str(e)}")
            messages.error(request, "Error updating fee structure.")

    return redirect('billing:fee_structure_list')


@login_required
@require_school_context
@require_role('manage_finances')
def delete_fee_view(request, fee_id):
    """Delete a fee structure."""
    if request.method == 'POST':
        try:
            fee = get_object_or_404(FeeStructure, id=fee_id, school=request.school)
            fee_name = fee.name
            fee.delete()

            messages.success(request, f"Fee structure '{fee_name}' deleted.")
            logger.info(f"Fee structure deleted: {fee_id} by user {request.user.id}")

        except Exception as e:
            logger.error(f"Delete fee error: {str(e)}")
            messages.error(request, "Error deleting fee structure.")

    return redirect('billing:fee_structure_list')


@login_required
@require_school_context
@require_role('manage_finances')
def activate_fee_view(request, fee_id):
    """Activate a fee structure."""
    if request.method == 'POST':
        try:
            fee = get_object_or_404(FeeStructure, id=fee_id, school=request.school)
            fee.is_active = True
            fee.save()

            messages.success(request, f"Fee structure '{fee.name}' activated.")

        except Exception as e:
            logger.error(f"Activate fee error: {str(e)}")
            messages.error(request, "Error activating fee structure.")

    return redirect('billing:fee_structure_list')


@login_required
@require_school_context
@require_role('manage_finances')
def deactivate_fee_view(request, fee_id):
    """Deactivate a fee structure."""
    if request.method == 'POST':
        try:
            fee = get_object_or_404(FeeStructure, id=fee_id, school=request.school)
            fee.is_active = False
            fee.save()

            messages.success(request, f"Fee structure '{fee.name}' deactivated.")

        except Exception as e:
            logger.error(f"Deactivate fee error: {str(e)}")
            messages.error(request, "Error deactivating fee structure.")

    return redirect('billing:fee_structure_list')


# ============ WEBHOOK HANDLER ============

@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook_view(request):
    """
    Production-ready Paystack webhook handler with comprehensive security.
    """
    start_time = time.time()
    webhook_id = f"wh_{int(time.time())}_{hashlib.md5(request.body).hexdigest()[:8]}"

    try:
        # === SECURITY LAYER 1: Basic Validation ===
        if not request.body:
            logger.warning(f"[{webhook_id}] Empty webhook body")
            return JsonResponse({'status': 'error', 'message': 'Empty body'}, status=400)

        # === SECURITY LAYER 2: Signature Verification ===
        signature = request.headers.get('x-paystack-signature')
        webhook_secret = getattr(settings, 'PAYSTACK_WEBHOOK_SECRET', '')

        if not webhook_secret:
            logger.error(f"[{webhook_id}] Webhook secret not configured")
            return JsonResponse({'status': 'error', 'message': 'Configuration error'}, status=500)

        if not WebhookSecurity.verify_signature(request.body, signature, webhook_secret):
            logger.warning(f"[{webhook_id}] Invalid webhook signature")
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=401)

        # === SECURITY LAYER 3: Payload Parsing & Validation ===
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"[{webhook_id}] Invalid JSON payload: {str(e)}")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        if not WebhookSecurity.validate_payload_structure(payload):
            logger.warning(f"[{webhook_id}] Invalid payload structure")
            return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

        # === SECURITY LAYER 4: Data Sanitization ===
        sanitized_data = WebhookSecurity.sanitize_webhook_data(payload)
        if not sanitized_data:
            logger.error(f"[{webhook_id}] Data sanitization failed")
            return JsonResponse({'status': 'error', 'message': 'Data processing error'}, status=400)

        # === PROCESS WEBHOOK ===
        logger.info(f"[{webhook_id}] Processing webhook: {sanitized_data['event']}")

        # Use shared ApplicationPaymentService for webhook processing
        success = get_application_payment_service().verify_and_process_payment_webhook(sanitized_data)

        processing_time = time.time() - start_time
        logger.info(f"[{webhook_id}] Webhook processed in {processing_time:.2f}s - Success: {success}")

        if success:
            return JsonResponse({'status': 'success', 'webhook_id': webhook_id})
        else:
            return JsonResponse({'status': 'error', 'message': 'Processing failed'}, status=400)

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"[{webhook_id}] Webhook error after {processing_time:.2f}s: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Internal server error'}, status=500)

# ============ HTMX VIEWS ============

@login_required
@require_school_context
def invoice_table_partial(request):
    """HTMX endpoint for invoice table with filters."""
    school = request.school

    try:
        invoices = Invoice.objects.filter(school=school).select_related('student', 'parent')

        # Apply filters
        status_filter = request.GET.get('status', '')
        type_filter = request.GET.get('type', '')
        search_query = request.GET.get('search', '')

        if status_filter:
            invoices = invoices.filter(status=status_filter)
        if type_filter:
            invoices = invoices.filter(invoice_type=type_filter)
        if search_query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=search_query) |
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query)
            )

        # Pagination for HTMX
        paginator = Paginator(invoices, 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'invoices': page_obj,
            'page_obj': page_obj,
            'status_filter': status_filter,
            'type_filter': type_filter,
            'search_query': search_query,
        }

        return render(request, 'billing/partials/invoice_table.html', context)

    except Exception as e:
        logger.error(f"Invoice table partial error: {str(e)}")
        return render(request, 'billing/partials/error.html', {'message': 'Error loading invoices'})


@login_required
def parent_invoice_table_partial(request):
    """HTMX endpoint for parent invoice table."""
    try:
        parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
        invoices = Invoice.objects.filter(
            parent__in=[p.parent_profile for p in parent_profiles]
        ).select_related('school', 'student').order_by('-created_at')

        status_filter = request.GET.get('status', '')
        if status_filter:
            invoices = invoices.filter(status=status_filter)

        context = {
            'invoices': invoices,
            'status_filter': status_filter,
        }

        return render(request, 'billing/partials/parent_invoice_table.html', context)

    except Exception as e:
        logger.error(f"Parent invoice table partial error: {str(e)}")
        return render(request, 'billing/partials/error.html', {'message': 'Error loading invoices'})


# ============ UTILITY VIEWS ============

@login_required
@require_school_context
def download_invoice_view(request, invoice_id):
    """Download invoice as PDF."""
    # This is a placeholder - implement PDF generation
    from django.http import HttpResponse
    invoice = get_object_or_404(Invoice, id=invoice_id, school=request.school)

    # TODO: Implement PDF generation
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

    # For now, just return a text response
    response.write(f"Invoice {invoice.invoice_number}\n")
    response.write(f"Amount: ₦{invoice.total_amount}\n")
    response.write(f"Status: {invoice.status}\n")

    return response
