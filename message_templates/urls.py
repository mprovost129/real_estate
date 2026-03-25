from django.urls import path

from . import views

app_name = "message_templates"

urlpatterns = [
    path("",                views.TemplateListView.as_view(),   name="list"),
    path("campaigns/",      views.CampaignListView.as_view(),   name="campaign_list"),
    path("campaigns/new/",  views.CampaignCreateView.as_view(), name="campaign_create"),
    path("campaigns/<int:pk>/", views.campaign_detail,          name="campaign_detail"),
    path("campaigns/<int:pk>/edit/", views.CampaignUpdateView.as_view(), name="campaign_update"),
    path("campaigns/<int:pk>/delete/", views.campaign_delete,   name="campaign_delete"),
    path("campaigns/<int:pk>/steps/add/", views.campaign_add_step, name="campaign_add_step"),
    path("campaigns/<int:pk>/steps/<int:step_pk>/delete/", views.campaign_delete_step, name="campaign_delete_step"),
    path("new/",            views.TemplateCreateView.as_view(),  name="create"),
    path("<int:pk>/",       views.TemplateDetailView.as_view(),  name="detail"),
    path("<int:pk>/edit/",  views.TemplateUpdateView.as_view(),  name="update"),
    path("<int:pk>/copy/",  views.template_duplicate,            name="duplicate"),
    path("<int:pk>/delete/",views.template_delete,               name="delete"),
    path("<int:pk>/preview/ajax/", views.template_preview_ajax,  name="preview_ajax"),
]
