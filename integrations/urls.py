from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("", views.integration_settings, name="settings"),
    path("<int:pk>/toggle-active/", views.integration_toggle_active, name="toggle_active"),
    path("oauth/<str:provider>/start/", views.oauth_start, name="oauth_start"),
    path("oauth/<str:provider>/callback/", views.oauth_callback, name="oauth_callback"),
]
