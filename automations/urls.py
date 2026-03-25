from django.urls import path

from . import views

app_name = "automations"

urlpatterns = [
    path("", views.AutomationRuleListView.as_view(), name="list"),
    path("test/", views.rule_test, name="test"),
    path("new/", views.AutomationRuleCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.AutomationRuleUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.rule_delete, name="delete"),
]
