from django.db import models

from .querysets import OrgScopedManager


class OrgScopedModel(models.Model):
    """
    Abstract base for any model that belongs to an Organization.
    Inherit from this instead of models.Model to get:
      - organization FK
      - OrgScopedManager (Contact.objects.for_org(org))
      - created_at / updated_at timestamps
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrgScopedManager()

    class Meta:
        abstract = True
