# shared/constants/model_fields.py

"""
CONSTANT field names to enforce consistency across the entire system.
NO DEPENDENCIES - can be created immediately.
"""

# Field name constants (prevent phone vs phone_number confusion)
PARENT_PHONE_FIELD = 'phone_number'  # ALWAYS use this for Parent model
PARENT_EMAIL_FIELD = 'email'

# Student model fields
STUDENT_CLASS_FIELD = 'current_class'  # ALWAYS core.Class, NEVER class_group
STUDENT_CLASS_ID_FIELD = 'current_class_id'

# Application model fields  
APPLICATION_CLASS_FIELD = 'proposed_class'  # core.Class foreign key
APPLICATION_STATUS_FIELD = 'status'

# Billing fields
INVOICE_AMOUNT_FIELD = 'amount'
INVOICE_STATUS_FIELD = 'payment_status'

# Permission constants
ROLE_FIELD = 'system_role_type'
SCHOOL_CONTEXT_FIELD = 'current_school'

# This kills ClassGroup references permanently
CLASS_MODEL_PATH = 'core.Class'  # ALWAYS use this
CLASS_ID_FIELD = 'class_id'  # For forms/APIs

# Form field → Model field mapping
FORM_TO_MODEL = {
    'phone': 'phone_number',  # Map ALL 'phone' form fields to 'phone_number'
    'class': 'current_class_id',  # Map 'class' from forms to core.Class
    'class_id': 'current_class_id',
    'class_group': 'current_class_id',  # REDIRECT ClassGroup to Class
    'class_group_id': 'current_class_id',  # KILL ClassGroup references
}

# Status choices (consolidated from all apps)
class StatusChoices:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    PAID = 'paid'
    UNPAID = 'unpaid'
    DRAFT = 'draft'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    SENT = 'sent'
    OVERDUE = 'overdue'
    PARTIALLY_PAID = 'Partially Paid'
    SUCCESS = 'success'
    FAILED = 'failed'
    REVERSED = 'failed'
    ABANDONED = 'abandoned'
    TRIALING = 'trialing'
    ACTIVE = 'Active'
    PAST_DUE = "Past Due"
    EXPIRED = 'expired'
    
# Payment methods
class PaymentMethods:
    PAYSTACK = 'paystack'
    CASH = 'cash'
    TRANSFER = 'transfer'
    WAIVER = 'waiver'