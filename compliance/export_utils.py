import csv
import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def build_audit_csv_payload(events):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "action",
            "severity",
            "actor_email",
            "entity_type",
            "entity_id",
            "message",
            "ip_address",
            "user_agent",
            "metadata",
        ]
    )
    row_count = 0
    for event in events:
        row_count += 1
        writer.writerow(
            [
                event.created_at.isoformat(),
                event.action,
                event.severity,
                event.actor.email if event.actor else "",
                event.entity_type,
                event.entity_id,
                event.message,
                event.ip_address or "",
                event.user_agent,
                event.metadata,
            ]
        )
    payload = buffer.getvalue().encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    return payload, row_count, checksum


def get_signing_key():
    key = getattr(settings, "COMPLIANCE_EXPORT_SIGNING_KEY", "") or settings.SECRET_KEY
    return str(key).encode("utf-8")


def sign_manifest(manifest):
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(get_signing_key(), manifest_bytes, hashlib.sha256).hexdigest()


def verify_manifest_signature(manifest, signature):
    expected = sign_manifest(manifest)
    return hmac.compare_digest(expected, signature or "")


def build_signed_zip_package(*, file_name, csv_payload, csv_sha256, row_count, organization_id, date_from, date_to):
    manifest = {
        "version": 1,
        "generated_at": timezone.now().isoformat(),
        "organization_id": organization_id,
        "file_name": file_name,
        "row_count": row_count,
        "csv_sha256": csv_sha256,
        "date_from": str(date_from or ""),
        "date_to": str(date_to or ""),
    }
    signature = sign_manifest(manifest)
    manifest["signature"] = signature

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit.csv", csv_payload)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    payload = stream.getvalue()
    package_sha256 = hashlib.sha256(payload).hexdigest()
    return payload, package_sha256, manifest, signature


def persist_export_artifact(*, payload, file_name):
    export_dir = Path(settings.MEDIA_ROOT) / "compliance_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / file_name
    path.write_bytes(payload)
    return str(path)


def _pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(lines, title="Compliance Export Summary"):
    """
    Build a minimal single-page PDF with plain text lines (no external deps).
    """
    safe_lines = [str(x) for x in (lines or [])]
    content_lines = [
        "BT",
        "/F1 12 Tf",
        "50 780 Td",
        f"({_pdf_escape(title)}) Tj",
        "0 -20 Td",
    ]
    for line in safe_lines[:40]:
        content_lines.append(f"({_pdf_escape(line)}) Tj")
        content_lines.append("0 -14 Td")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n"
    )

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)
    xref_start = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.write(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.write(
        (
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return pdf.getvalue()


def build_signed_zip_package_with_pdf(
    *,
    file_name,
    csv_payload,
    csv_sha256,
    row_count,
    organization_id,
    date_from,
    date_to,
    pdf_payload,
    pdf_sha256,
):
    manifest = {
        "version": 2,
        "generated_at": timezone.now().isoformat(),
        "organization_id": organization_id,
        "file_name": file_name,
        "row_count": row_count,
        "csv_sha256": csv_sha256,
        "pdf_sha256": pdf_sha256,
        "date_from": str(date_from or ""),
        "date_to": str(date_to or ""),
    }
    signature = sign_manifest(manifest)
    manifest["signature"] = signature

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit.csv", csv_payload)
        zf.writestr("summary.pdf", pdf_payload)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    payload = stream.getvalue()
    package_sha256 = hashlib.sha256(payload).hexdigest()
    return payload, package_sha256, manifest, signature
