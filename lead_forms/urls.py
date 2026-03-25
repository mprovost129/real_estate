from django.urls import path

from . import views

app_name = "lead_forms"

urlpatterns = [
    # Management (authenticated)
    path("",                  views.FormListView.as_view(),   name="list"),
    path("new/",              views.FormCreateView.as_view(), name="create"),
    path("<int:pk>/",         views.form_detail,              name="detail"),
    path("<int:pk>/edit/",    views.FormUpdateView.as_view(), name="update"),
    path("<int:pk>/toggle/",  views.form_toggle,              name="toggle"),
    path("<int:pk>/delete/",  views.form_delete,              name="delete"),

    # Public (no auth)
    path("f/<slug:slug>/",   views.public_form,              name="public_form"),
]
