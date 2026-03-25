from django.apps import AppConfig


class PipelinesConfig(AppConfig):
    name = 'pipelines'

    def ready(self):
        import pipelines.signals  # noqa: F401
