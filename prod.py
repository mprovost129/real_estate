"""
Compatibility shim for deployments that set DJANGO_SETTINGS_MODULE=prod.
Prefer using DJANGO_SETTINGS_MODULE=config.settings.prod.
"""

from config.settings.prod import *  # noqa: F401,F403
