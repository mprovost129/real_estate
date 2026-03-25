import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Command(BaseCommand):
    help = "Create (if missing) and verify the PostgreSQL schema used for tenant isolation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default=None,
            help="Schema to ensure. Defaults to settings.DB_SCHEMA.",
        )

    def handle(self, *args, **options):
        schema = (options.get("schema") or getattr(settings, "DB_SCHEMA", "public") or "public").strip()
        if not SCHEMA_RE.match(schema):
            raise CommandError(
                f"Invalid schema name '{schema}'. Use letters, numbers, and underscores only."
            )

        vendor = connection.vendor
        if vendor != "postgresql":
            self.stdout.write(
                self.style.WARNING(
                    f"Database vendor is '{vendor}'. Schema isolation command is PostgreSQL-specific; skipping."
                )
            )
            return

        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", [schema])
            exists = cursor.fetchone() is not None

        if not exists:
            raise CommandError(f"Failed to verify schema '{schema}'.")

        self.stdout.write(self.style.SUCCESS(f"Schema '{schema}' is ready."))
