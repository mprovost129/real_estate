from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.templatetags.static import static as static_url
from django.urls import include, path
from django.views.generic import RedirectView

from organizations import views as org_views
from users import views as user_views

urlpatterns = [
    path("", lambda request: redirect("dashboard"), name="home"),
    path("favicon.ico", RedirectView.as_view(url=static_url("images/favicon.svg"), permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("users.urls")),
    path("contacts/", include("contacts.urls")),
    path("pipelines/", include("pipelines.urls")),
    path("tasks/", include("tasks.urls")),
    path("properties/", include("properties.urls")),
    path("reports/", include("reports.urls")),
    path("open-houses/", include("open_houses.urls")),
    path("transactions/", include("transactions.urls")),
    path("templates/", include("message_templates.urls")),
    path("notifications/", include("notifications.urls")),
    path("forms/",         include("lead_forms.urls")),
    path("automations/",   include("automations.urls")),
    path("compliance/", include("compliance.urls")),

    # Settings
    path("settings/profile/",                   user_views.profile_settings,            name="profile_settings"),
    path("settings/organization/",              org_views.org_settings,                 name="org_settings"),
    path("settings/team/",                      org_views.team_settings,                name="team_settings"),
    path("settings/integrations/",              include(("integrations.urls", "integrations"), namespace="integrations")),
    path("settings/team/<int:pk>/role/",        org_views.team_member_role,             name="team_member_role"),
    path("settings/team/<int:pk>/remove/",      org_views.team_member_remove,           name="team_member_remove"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
