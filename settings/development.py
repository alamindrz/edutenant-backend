# settings/development.py
"""
Development settings for Edusuite project.
"""
from .base import *

# Debug settings
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '.serveo.net', '.lhr.life']





# Django Debug Toolbar
INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

# Debug toolbar configuration
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: True,
}

# Database configuration for development
DATABASES['default'].update({
    'ATOMIC_REQUESTS': True,
})

# Email configuration for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Static files in development
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Paystack test keys
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', 'pk_test_your_test_key_here')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_your_test_key_here')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET', 'whsec_test_webhook_secret')

# Logging configuration for development
LOGGING['handlers']['file'] = {
    'level': 'DEBUG',
    'class': 'logging.FileHandler',
    'filename': BASE_DIR / 'logs' / 'development.log',
    'formatter': 'verbose',
}

LOGGING['handlers']['billing_file'] = {
    'level': 'DEBUG',
    'class': 'logging.FileHandler',
    'filename': BASE_DIR / 'logs' / 'billing_development.log',
    'formatter': 'verbose',
}

LOGGING['loggers']['django']['handlers'] = ['console', 'file']
LOGGING['loggers']['billing']['handlers'] = ['console', 'billing_file']
LOGGING['loggers']['attendance']['handlers'] = ['console', 'file']

# Disable security settings for development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# CORS settings for development
CORS_ALLOWED_ORIGINS += [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Allow all origins in development (be careful with this)
CORS_ALLOW_ALL_ORIGINS = True

# Cache configuration for development
CACHES['default'] = {
    'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
}

# Allauth development settings
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Disable email verification in development