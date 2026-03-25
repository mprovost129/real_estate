"""Default settings loader.

Uses development settings locally and production settings on Render or when
DJANGO_ENV is explicitly set to production.
"""

import os


environment = os.environ.get('DJANGO_ENV', '').strip().lower()
is_render = os.environ.get('RENDER', '').strip().lower() == 'true'

if environment in {'prod', 'production'} or is_render:
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403