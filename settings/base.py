# settings/base.py - FIXED
"""
Base settings for Edusuite project.
"""

import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key
import logging

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', get_random_secret_key())

# Application definition
INSTALLED_APPS = [
    'django.contrib.sites',  # Required by allauth
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Third party apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'corsheaders',
    'rest_framework',
    
    # Local apps
    'core',
    'users',
    'students',
    'billing',
    'admissions',
    'attendance',
    'shared',
    'mathfilters',
]

SITE_ID = 1

# FIXED: Proper middleware order
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    
    # Django core middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # Add CORS if you have CORS_ORIGIN_ALLOW_ALL=True
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom middleware (FIXED order)
    'core.middleware.SessionValidationMiddleware',  # Must come after SessionMiddleware
    'core.middleware.SchoolMiddleware',  # Before TimezoneMiddleware
    'core.middleware.TimezoneMiddleware',
    'core.middleware.NotificationMiddleware',
    'core.middleware.WhiteLabelMiddleware',
    
    # Allauth (must be after authentication middleware)
    'allauth.account.middleware.AccountMiddleware',
    
    # Security and logging (end of chain)
    'core.middleware.SecurityHeadersMiddleware',
    'core.middleware.RequestLoggingMiddleware',
    'core.middleware.ExceptionHandlingMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # Required by allauth
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'shared.context_processors.unified_context',  # our unified context processor
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Remove or comment out Whitenoise if not installed
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'users.User'

# Allauth Configuration
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SESSION_REMEMBER = True

# Login URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'  # Will be handled by dashboard_router
LOGOUT_REDIRECT_URL = '/'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',  # Keep for development
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
    }
}

# CORS settings (FIXED - enable for development)
if os.getenv('DEBUG', 'True').lower() == 'true':
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [
        "https://edusuite.com",
        "https://*.edusuite.com",
    ]

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "102.212.246.160",  # Your server IP
]

# Add wildcard for subdomains
ALLOWED_HOSTS += ['.localhost', '127.0.0.1']  # Allow subdomains in development

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Console for development

# For production, use:
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
# EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
# EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
# EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
# EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
# DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Edusuite <noreply@edusuite.com>')

# Paystack Configuration
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET', '')

# Cache configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Use db for now
SESSION_COOKIE_AGE = 1209600  # 2 weeks in seconds
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = 'edusuite_session'
SESSION_SAVE_EVERY_REQUEST = True  # Helpful for session updates

# Security settings (base - will be overridden in production)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',  # Changed to DEBUG for development
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'shared': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# DEFAULT TIMEZONE for middleware
DEFAULT_TIMEZONE = 'Africa/Lagos'

# IMPORTANT: Remove or fix the broken import at the end
# Comment out or fix this line:
# from .billing_settings import *
# If billing_settings.py doesn't exist, remove this line# Triggering Sourcery Scan 
