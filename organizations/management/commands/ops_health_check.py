import json

from django.core.management.base import BaseCommand, CommandError

from organizations.models import Organization
from organizations.ops import run_ops_health_check


class Command(BaseCommand):
    help = "Run the Ops Center full health check suite."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None, help="Organization id. Defaults to first organization.")
        parser.add_argument("--json", action="store_true", help="Emit JSON output.")
        parser.add_argument("--fail-on-warning", action="store_true", help="Exit non-zero when warnings are present.")

    def handle(self, *args, **options):
        org_id = options["org_id"]
        org = Organization.objects.filter(pk=org_id).first() if org_id else Organization.objects.order_by("id").first()
        if not org:
            raise CommandError("No organization found. Create one before running ops_health_check.")

        report = run_ops_health_check(organization=org)
        payload = {
            "overall": report["overall"],
            "counts": report["counts"],
            "results": [
                {
                    "key": item.key,
                    "label": item.label,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in report["results"]
            ],
        }

        if options["json"]:
            self.stdout.write(json.dumps(payload))
        else:
            self.stdout.write(
                f"overall={payload['overall']} pass={payload['counts']['pass']} "
                f"warn={payload['counts']['warn']} fail={payload['counts']['fail']}"
            )
            for item in payload["results"]:
                self.stdout.write(f"[{item['status'].upper()}] {item['label']} - {item['detail']}")

        should_fail = payload["overall"] == "fail" or (
            options["fail_on_warning"] and payload["counts"]["warn"] > 0
        )
        if should_fail:
            raise SystemExit(1)
