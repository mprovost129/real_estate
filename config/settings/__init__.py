"""Default settings loader.

Uses production settings whenever the environment clearly indicates a hosted
deployment, including existing Render services that may not yet use
render.yaml.
"""

import os


environment = os.environ.get('DJANGO_ENV', '').strip().lower()
is_render = os.environ.get('RENDER', '').strip().lower() == 'true'
has_database_url = bool(os.environ.get('DATABASE_URL', '').strip())
has_render_hostname = bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip())

if environment in {'prod', 'production'} or is_render or has_database_url or has_render_hostname:
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403