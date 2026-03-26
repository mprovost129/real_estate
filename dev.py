"""
Compatibility shim for local setups that set DJANGO_SETTINGS_MODULE=dev.
Prefer using DJANGO_SETTINGS_MODULE=config.settings.dev.
"""

from config.settings.dev import *  # noqa: F401,F403
