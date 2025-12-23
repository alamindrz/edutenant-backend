# settings/billing.py
"""
Billing and Paystack configuration for Edusuite.
"""

import os
from django.conf import settings

# Paystack Configuration
PAYSTACK_PUBLIC_KEY = getattr(settings, 'PAYSTACK_PUBLIC_KEY', os.getenv('PAYSTACK_PUBLIC_KEY'))
PAYSTACK_SECRET_KEY = getattr(settings, 'PAYSTACK_SECRET_KEY', os.getenv('PAYSTACK_SECRET_KEY'))
PAYSTACK_WEBHOOK_SECRET = getattr(settings, 'PAYSTACK_WEBHOOK_SECRET', os.getenv('PAYSTACK_WEBHOOK_SECRET'))

# Billing Configuration
BILLING_SETTINGS = {
    'PLATFORM_FEE_PERCENT': 0.015,  # 1.5%
    'PAYSTACK_FEE_PERCENT': 0.015,  # 1.5%
    'PAYSTACK_FIXED_FEE': 15.00,    # ₦15
    'DEFAULT_CURRENCY': 'NGN',
    'ALLOW_PARTIAL_PAYMENTS': False,
    'AUTO_MARK_OVERDUE_DAYS': 1,
    'RENEWAL_REMINDER_DAYS': 7,
    'INVOICE_PREFIX': 'INV',
    'APPLICATION_PREFIX': 'APP',
    'ADMISSION_PREFIX': 'ADM',
}

# Subscription Plans (in Naira)
SUBSCRIPTION_PLANS = {
    'basic': {
        'name': 'Basic Plan',
        'price_monthly': 0,
        'price_yearly': 0,
        'max_students': 50,
        'max_staff': 5,
        'features': [
            'Path-based URL (edusuite.com/yourschool)',
            'Basic student management',
            'Fee management',
            'Parent portal',
            'Email support'
        ]
    },
    'standard': {
        'name': 'Standard Plan',
        'price_monthly': 5000,  # ₦5,000/month
        'price_yearly': 50000,  # ₦50,000/year
        'max_students': 200,
        'max_staff': 20,
        'features': [
            'Custom subdomain (yourschool.edusuite.com)',
            'Advanced student management',
            'Payment processing',
            'Attendance tracking',
            'Grade management',
            'Priority support'
        ]
    },
    'premium': {
        'name': 'Premium Plan',
        'price_monthly': 10000,  # ₦10,000/month
        'price_yearly': 100000,  # ₦100,000/year
        'max_students': 1000,
        'max_staff': 100,
        'features': [
            'White-label branding',
            'Advanced analytics',
            'Custom reports',
            'API access',
            'Dedicated support',
            'SMS notifications'
        ]
    }
}

# Nigerian Bank Codes (Common banks)
NIGERIAN_BANKS = {
    '044': 'Access Bank',
    '063': 'Diamond Bank',
    '050': 'Ecobank Nigeria',
    '070': 'Fidelity Bank',
    '011': 'First Bank of Nigeria',
    '214': 'First City Monument Bank',
    '058': 'Guaranty Trust Bank',
    '030': 'Heritage Bank',
    '301': 'Jaiz Bank',
    '082': 'Keystone Bank',
    '014': 'MainStreet Bank',
    '076': 'Polaris Bank',
    '101': 'Providus Bank',
    '221': 'Stanbic IBTC Bank',
    '068': 'Standard Chartered Bank',
    '232': 'Sterling Bank',
    '100': 'Suntrust Bank',
    '032': 'Union Bank of Nigeria',
    '033': 'United Bank for Africa',
    '215': 'Unity Bank',
    '035': 'Wema Bank',
    '057': 'Zenith Bank',
}

# Fee Categories for Nigerian Schools
FEE_CATEGORIES = [
    {'name': 'Tuition & Academic', 'order': 1},
    {'name': 'Application & Registration', 'order': 2},
    {'name': 'Development & PTA', 'order': 3},
    {'name': 'Books & Materials', 'order': 4},
    {'name': 'Uniform & Clothing', 'order': 5},
    {'name': 'Medical & Health', 'order': 6},
    {'name': 'Sports & Activities', 'order': 7},
    {'name': 'Transportation', 'order': 8},
    {'name': 'Boarding', 'order': 9},
    {'name': 'Other Fees', 'order': 10},
]

def get_paystack_config():
    """Get Paystack configuration with validation."""
    if not PAYSTACK_SECRET_KEY:
        raise ValueError("PAYSTACK_SECRET_KEY is required for payment processing")

    return {
        'public_key': PAYSTACK_PUBLIC_KEY,
        'secret_key': PAYSTACK_SECRET_KEY,
        'webhook_secret': PAYSTACK_WEBHOOK_SECRET,
    }

def validate_billing_config():
    """Validate billing configuration on startup."""
    required_settings = ['PAYSTACK_PUBLIC_KEY', 'PAYSTACK_SECRET_KEY']

    for setting in required_settings:
        if not getattr(settings, setting, None):
            print(f"Warning: {setting} is not configured. Payment features will not work.")

    # Validate subscription plans
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        if plan['price_monthly'] < 0 or plan['price_yearly'] < 0:
            raise ValueError(f"Invalid price in {plan_id} plan")

    return True
