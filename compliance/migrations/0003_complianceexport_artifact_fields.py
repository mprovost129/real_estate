from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0002_complianceexport"),
    ]

    operations = [
        migrations.AddField(
            model_name="complianceexport",
            name="artifact_path",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="complianceexport",
            name="manifest",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="complianceexport",
            name="signature",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name="complianceexport",
            name="export_format",
            field=models.CharField(choices=[("csv", "CSV"), ("zip", "ZIP Package")], default="csv", max_length=10),
        ),
    ]
