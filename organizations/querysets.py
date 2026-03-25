from django.db import models


class OrgScopedQuerySet(models.QuerySet):
    """
    Base QuerySet for any model that belongs to an Organization.
    Usage:
        objects = OrgScopedManager()

    Then in views / business logic:
        Contact.objects.for_org(org)
    """

    def for_org(self, organization):
        return self.filter(organization=organization)

    def active(self):
        return self.filter(is_active=True)


class OrgScopedManager(models.Manager):
    def get_queryset(self):
        return OrgScopedQuerySet(self.model, using=self._db)

    def for_org(self, organization):
        return self.get_queryset().for_org(organization)

    def active(self):
        return self.get_queryset().active()
