import hashlib
import json
import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from compliance.export_utils import verify_manifest_signature
from compliance.models import ComplianceExport


class Command(BaseCommand):
    help = "Verify compliance export artifacts against stored hashes/signatures."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max number of exports to verify.")
        parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero if any export fails verification.")

    def handle(self, *args, **options):
        limit = options["limit"]
        fail_on_error = options["fail_on_error"]

        exports = ComplianceExport.objects.select_related("organization").order_by("-created_at")[:limit]
        failures = []
        checked = 0

        for ex in exports:
            checked += 1
            try:
                self._verify_export(ex)
                self.stdout.write(self.style.SUCCESS(f"OK: {ex.file_name} ({ex.export_format})"))
            except Exception as exc:
                msg = f"FAIL: {ex.file_name} ({ex.export_format}) - {exc}"
                failures.append(msg)
                self.stdout.write(self.style.ERROR(msg))

        self.stdout.write(
            self.style.WARNING(
                f"Verified {checked} export(s); failures={len(failures)}."
            )
        )
        if fail_on_error and failures:
            raise CommandError(f"Verification failed for {len(failures)} export(s).")

    def _verify_export(self, ex):
        if not ex.artifact_path:
            raise ValueError("artifact_path missing")
        path = Path(ex.artifact_path)
        if not path.exists():
            raise ValueError("artifact file not found")
        payload = path.read_bytes()
        payload_sha = hashlib.sha256(payload).hexdigest()
        if payload_sha != ex.sha256:
            raise ValueError("payload sha256 mismatch")

        if ex.export_format == ComplianceExport.ExportFormat.CSV:
            return

        if ex.export_format == ComplianceExport.ExportFormat.ZIP:
            with zipfile.ZipFile(path, "r") as zf:
                if "manifest.json" not in zf.namelist() or "audit.csv" not in zf.namelist():
                    raise ValueError("zip missing manifest.json or audit.csv")
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                signature = manifest.get("signature", "")
                manifest_without_sig = {k: v for k, v in manifest.items() if k != "signature"}
                if not verify_manifest_signature(manifest_without_sig, signature):
                    raise ValueError("manifest signature invalid")
                csv_bytes = zf.read("audit.csv")
                csv_sha = hashlib.sha256(csv_bytes).hexdigest()
                if csv_sha != manifest.get("csv_sha256"):
                    raise ValueError("manifest csv hash mismatch")
                if "pdf_sha256" in manifest:
                    if "summary.pdf" not in zf.namelist():
                        raise ValueError("manifest expects summary.pdf but file is missing")
                    pdf_bytes = zf.read("summary.pdf")
                    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
                    if pdf_sha != manifest.get("pdf_sha256"):
                        raise ValueError("manifest pdf hash mismatch")
                if ex.signature and ex.signature != signature:
                    raise ValueError("stored signature mismatch")
            return

        raise ValueError("unsupported export format")
