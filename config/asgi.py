"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

if os.environ.get('DJANGO_SETTINGS_MODULE') == 'prod':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.prod'
elif os.environ.get('DJANGO_SETTINGS_MODULE') == 'dev':
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.dev'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

application = get_asgi_application()
