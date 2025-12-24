# billing/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
    verbose_name = 'Billing & Payments'

    def ready(self):
        """Initialize billing system on app startup."""
        try:
            # Import signals
            from . import signals
            logger.info("Billing app initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing billing app: {str(e)}")
