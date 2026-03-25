from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pipelines", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinestage",
            name="enforce_requirements",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, block stage moves if form/automation requirements are unmet.",
            ),
        ),
        migrations.AddField(
            model_name="pipelinestage",
            name="required_automation_rule_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of AutomationRule IDs that must be active for this stage.",
            ),
        ),
        migrations.AddField(
            model_name="pipelinestage",
            name="required_form_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of LeadCaptureForm IDs required for this stage.",
            ),
        ),
        migrations.AddField(
            model_name="pipelinestage",
            name="required_tasks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of task definitions to create/check on stage entry. Example: [{"title":"Send disclosure","task_type":"document","due_in_days":0,"priority":"high"}]',
            ),
        ),
    ]
