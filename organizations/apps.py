from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = 'organizations'

    def ready(self):
        # Register Django system checks for org/workspace safety.
        from . import checks  # noqa: F401
