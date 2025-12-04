# billing/views.py
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
import json

from core.decorators import require_role, require_school_context
from .models import Invoice, Transaction, FeeStructure, SubdomainPlan, SchoolSubscription
from .services import BillingService, PaystackService
from core.exceptions import PaymentProcessingError
import hashlib
import hmac
import time
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods




logger = logging.getLogger(__name__)


@login_required
@require_school_context
@require_role('manage_finances')
def billing_dashboard_view(request):
    """Billing dashboard for school administrators."""
    school = request.school
    
    try:
        # Financial statistics
        financial_stats = {
            'total_revenue': Invoice.objects.filter(
                school=school, status='paid'
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'pending_invoices': Invoice.objects.filter(
                school=school, status__in=['sent', 'overdue']
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'total_invoices': Invoice.objects.filter(school=school).count(),
            'paid_invoices': Invoice.objects.filter(school=school, status='paid').count(),
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


@login_required
@require_school_context
@require_role('manage_finances')
def invoice_list_view(request):
    """List all invoices for the school."""
    school = request.school
    
    try:
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
        
        context = {
            'invoices': page_obj,
            'status_filter': status_filter,
            'type_filter': type_filter,
            'search_query': search_query,
            'page_obj': page_obj,
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


@login_required
@require_school_context
@require_role('manage_finances')
def fee_structure_list_view(request):
    """Manage fee structures for the school."""
    school = request.school
    
    try:
        fee_structures = FeeStructure.objects.filter(school=school).select_related('category').order_by('category__order', 'fee_type')
        
        # Group by category for better organization
        fees_by_category = {}
        for fee in fee_structures:
            category_name = fee.category.name if fee.category else 'Uncategorized'
            if category_name not in fees_by_category:
                fees_by_category[category_name] = []
            fees_by_category[category_name].append(fee)
        
        context = {
            'fees_by_category': fees_by_category,
            'fee_structures': fee_structures,
        }
        
        return render(request, 'billing/fee_structure_list.html', context)
        
    except Exception as e:
        logger.error(f"Fee structure list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading fee structures.")
        return redirect('billing:dashboard')


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
        
        # Calculate totals
        total_pending = sum(inv.total_amount for inv in invoices if inv.status in ['sent', 'overdue'])
        total_paid = sum(inv.total_amount for inv in invoices if inv.status == 'paid')
        
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
                paystack_service = PaystackService()
                
                if len(invoices) == 1:
                    # Single invoice payment
                    payment_data = paystack_service.initialize_payment(
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
                    
                    # Create combined payment record (simplified - in production, create a combined invoice)
                    messages.info(request, 
                        f"Preparing payment of ₦{total_selected:,.2f} for {len(selected_invoices)} invoice(s)."
                    )
                    # Redirect to combined payment processing
                    return redirect('billing:combined_payment', invoice_ids=','.join(str(i.id) for i in selected_invoices))
                    
            except PaymentProcessingError as e:
                messages.error(request, str(e))
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


@login_required
def payment_success_view(request):
    """Payment success callback."""
    try:
        reference = request.GET.get('reference')
        if not reference:
            messages.error(request, "No payment reference provided.")
            return redirect('billing:parent_invoices')
        
        # Verify payment
        paystack_service = PaystackService()
        verification = paystack_service.verify_transaction(reference)
        
        if verification['status'] == 'success':
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


@csrf_exempt
@require_http_methods(["POST"])
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
        
        success = BillingService.process_payment_webhook(sanitized_data)
        
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

# HTMX Views
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
        
        context = {
            'invoices': invoices,
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