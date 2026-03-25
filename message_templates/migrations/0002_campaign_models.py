from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("message_templates", "0001_initial"),
        ("contacts", "0002_contactnote_call_direction_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DripCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], default="email", max_length=10)),
                ("category", models.CharField(choices=[("buyer_lead", "Buyer Lead"), ("seller_lead", "Seller Lead"), ("open_house", "Open House"), ("past_client", "Past Client"), ("sphere", "Sphere / Referral"), ("transaction", "Transaction"), ("nurture", "Long-Term Nurture"), ("general", "General")], default="general", max_length=20)),
                ("enroll_contact_type", models.CharField(blank=True, help_text="Optional contact type filter for automatic enrollment.", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_campaigns", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="organizations.organization")),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("organization", "name")},
            },
        ),
        migrations.CreateModel(
            name="CampaignEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("completed", "Completed"), ("paused", "Paused"), ("unsubscribed", "Unsubscribed")], default="active", max_length=15)),
                ("last_step_order", models.PositiveSmallIntegerField(default=0)),
                ("next_run_at", models.DateTimeField(blank=True, null=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="message_templates.dripcampaign")),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="campaign_enrollments", to="contacts.contact")),
                ("enrolled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="campaign_enrollments_created", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="organizations.organization")),
            ],
            options={
                "ordering": ["next_run_at", "created_at"],
                "unique_together": {("campaign", "contact")},
            },
        ),
        migrations.CreateModel(
            name="DripCampaignStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(default=1)),
                ("delay_days", models.PositiveSmallIntegerField(default=0, help_text="Days to wait before this step runs after the previous step.")),
                ("is_active", models.BooleanField(default=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="message_templates.dripcampaign")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="campaign_steps", to="message_templates.messagetemplate")),
            ],
            options={
                "ordering": ["campaign", "order"],
                "unique_together": {("campaign", "order")},
            },
        ),
        migrations.CreateModel(
            name="CampaignSendLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], max_length=10)),
                ("status", models.CharField(choices=[("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")], default="sent", max_length=10)),
                ("detail", models.TextField(blank=True)),
                ("provider_message_id", models.CharField(blank=True, max_length=120)),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="campaign_send_logs", to="contacts.contact")),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="send_logs", to="message_templates.campaignenrollment")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="organizations.organization")),
                ("step", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="send_logs", to="message_templates.dripcampaignstep")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
