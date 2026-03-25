import os

from django.conf import settings
from django.core.checks import Warning, register


@register()
def shared_db_schema_check(app_configs, **kwargs):
    """
    Warn when hosted/prod deployments are still using the public schema.
    """
    db_schema = (getattr(settings, "DB_SCHEMA", "public") or "public").strip().lower()
    is_hosted = (
        os.environ.get("RENDER", "").strip().lower() == "true"
        or bool(os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip())
        or bool(os.environ.get("DATABASE_URL", "").strip())
    )
    is_prod_like = is_hosted or not bool(getattr(settings, "DEBUG", False))

    if is_prod_like and db_schema == "public":
        return [
            Warning(
                "DB_SCHEMA is set to 'public' in a production/hosted environment.",
                hint=(
                    "Set a unique DB_SCHEMA per deployment (for example, "
                    "'real_estate_site_a') and run `manage.py ensure_db_schema` "
                    "then `manage.py migrate`."
                ),
                id="organizations.W001",
            )
        ]
    return []
