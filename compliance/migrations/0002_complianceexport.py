from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplianceExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("export_format", models.CharField(choices=[("csv", "CSV")], default="csv", max_length=10)),
                ("date_from", models.DateField(blank=True, null=True)),
                ("date_to", models.DateField(blank=True, null=True)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("sha256", models.CharField(max_length=64)),
                ("file_name", models.CharField(blank=True, max_length=255)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="compliance_complianceexport_set", to="organizations.organization")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="compliance_exports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
