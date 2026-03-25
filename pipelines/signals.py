from django.db.models.signals import post_save
from django.dispatch import receiver

from organizations.models import Organization

from .defaults import create_default_pipelines


@receiver(post_save, sender=Organization)
def bootstrap_pipelines(sender, instance, created, **kwargs):
    if created:
        create_default_pipelines(instance)
