from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("",           views.overview,         name="overview"),
    path("contacts/",  views.contacts_report,  name="contacts"),
    path("pipeline/",  views.pipeline_report,  name="pipeline"),
    path("tasks/",        views.tasks_report,        name="tasks"),
    path("transactions/", views.transactions_report,  name="transactions"),
    path("compliance/", views.compliance_report, name="compliance"),
]
