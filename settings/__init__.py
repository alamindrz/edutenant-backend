# settings/__init__.py
import os

DJANGO_ENV = os.getenv("DJANGO_ENV", "development").lower()

if DJANGO_ENV == "production":
    print("⚙️ Using PRODUCTION settings")
    from .production import *
else:
    print("🛠️ Using DEVELOPMENT settings")
    from .development import *
