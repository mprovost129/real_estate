import logging

from django.conf import settings
from django.db import DatabaseError

from organizations.models import Membership, Organization

from .models import User

logger = logging.getLogger(__name__)


def ensure_test_login_user(email: str, raw_password: str):
    """Create/update a deterministic test account when fallback login is enabled."""
    if not getattr(settings, "ENABLE_TEST_LOGIN", False):
        return None

    configured_email = getattr(settings, "TEST_LOGIN_EMAIL", "").lower().strip()
    configured_password = getattr(settings, "TEST_LOGIN_PASSWORD", "")
    if not configured_email or not configured_password:
        return None

    if (email or "").lower().strip() != configured_email or raw_password != configured_password:
        return None

    user, _ = User.objects.get_or_create(
        email=configured_email,
        defaults={
            "first_name": getattr(settings, "TEST_LOGIN_FIRST_NAME", "Render"),
            "last_name": getattr(settings, "TEST_LOGIN_LAST_NAME", "Tester"),
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    user.first_name = getattr(settings, "TEST_LOGIN_FIRST_NAME", "Render")
    user.last_name = getattr(settings, "TEST_LOGIN_LAST_NAME", "Tester")
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(configured_password)
    user.save(
        update_fields=[
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "password",
        ]
    )

    try:
        org, _ = Organization.objects.get_or_create(
            name=getattr(settings, "TEST_LOGIN_ORG_NAME", "Render Test Workspace"),
            defaults={
                "owner": user,
                "org_type": Organization.OrgType.INDIVIDUAL,
                "plan": Organization.Plan.FREE,
                "is_active": True,
            },
        )
        if org.owner_id != user.id or not org.is_active:
            org.owner = user
            org.is_active = True
            org.save(update_fields=["owner", "is_active", "updated_at"])

        Membership.objects.update_or_create(
            user=user,
            organization=org,
            defaults={
                "role": Membership.Role.OWNER,
                "is_active": True,
            },
        )
    except DatabaseError:
        logger.warning("Test login user created without org bootstrap due to database state.")

    return user
