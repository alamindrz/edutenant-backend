# settings/__init__.py
from .base import *
from .development import *

# Determine which settings to use based on environment
if os.getenv('DJANGO_SETTINGS_MODULE') == 'config.settings.production':
    from .production import *