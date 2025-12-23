# settings/production.py
"""
Production settings for Edutenant - Secure and optimized.
"""

import os
from .base import *

# Security settings
DEBUG = False
ALLOWED_HOSTS = [
    'edutenant.com',
    'www.edutenant.com',
    '*.edutenant.com',  # For school subdomains
    '.edutenant.com',   # Allow all subdomains
    '102.212.246.160',
]

# SSL/HTTPS settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Paystack Production Keys
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY_LIVE')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY_LIVE')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET_LIVE')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
        'CONN_MAX_AGE': 600,  # 10 minutes
        'OPTIONS': {
            'sslmode': 'require',
        }
    }
}

# Cache for idempotency and performance
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'edutenant'
    }
}

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", "message": "%(message)s", "webhook_id": "%(webhook_id)s"}',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/edutenant/edutenant.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'billing_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/edutenant/billing.log',
            'maxBytes': 10485760,
            'backupCount': 10,
            'formatter': 'json',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/edutenant/error.log',
            'maxBytes': 10485760,
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'error_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'billing': {
            'handlers': ['billing_file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
} 