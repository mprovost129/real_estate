from django.urls import path

from . import views

app_name = "compliance"

urlpatterns = [
    path("", views.compliance_dashboard, name="dashboard"),
    path("export/audit.csv", views.export_audit_csv, name="export_audit_csv"),
    path("export/audit-package.zip", views.export_audit_package, name="export_audit_package"),
]
