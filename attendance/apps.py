# attendance/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attendance'
    verbose_name = 'Attendance Management'
    
    def ready(self):
        """Initialize attendance app."""
        try:
            from . import signals
            logger.info("Attendance app initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing attendance app: {str(e)}") 