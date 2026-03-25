import json

from django.core.checks import run_checks
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validate DB schema isolation checks and optionally fail on warnings/errors."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Exit non-zero when warning-level isolation checks are present.",
        )

    def handle(self, *args, **options):
        messages = run_checks()
        isolation_messages = [m for m in messages if getattr(m, "id", "").startswith("organizations.W")]

        warning_count = sum(1 for m in isolation_messages if m.level == 30)
        error_count = sum(1 for m in isolation_messages if m.level >= 40)

        payload = {
            "checks": [
                {
                    "id": m.id,
                    "level": m.level,
                    "message": str(m.msg),
                    "hint": str(m.hint or ""),
                }
                for m in isolation_messages
            ],
            "warning_count": warning_count,
            "error_count": error_count,
            "status": "ok",
        }

        if error_count > 0 or (options["fail_on_warning"] and warning_count > 0):
            payload["status"] = "fail"

        if options["json"]:
            self.stdout.write(json.dumps(payload))
        else:
            if isolation_messages:
                for item in payload["checks"]:
                    self.stdout.write(
                        f"{item['id']} level={item['level']} message={item['message']} hint={item['hint']}"
                    )
            else:
                self.stdout.write("No DB isolation warnings.")
            self.stdout.write(
                f"summary status={payload['status']} warnings={warning_count} errors={error_count}"
            )

        if payload["status"] == "fail":
            raise SystemExit(1)
