from django.urls import path

from . import views

app_name = "open_houses"

urlpatterns = [
    path("",                                             views.OpenHouseListView.as_view(),   name="list"),
    path("new/",                                         views.OpenHouseCreateView.as_view(), name="create"),
    path("<int:pk>/",                                    views.OpenHouseDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/",                               views.OpenHouseUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/",                             views.open_house_delete,             name="delete"),
    path("<int:pk>/add-visitor/",                        views.add_visitor,                   name="add_visitor"),
    path("<int:pk>/visitor/<int:visitor_pk>/convert/",   views.convert_visitor,               name="convert_visitor"),
    path("<int:pk>/visitor/<int:visitor_pk>/followup/",  views.mark_followed_up,              name="mark_followed_up"),
    path("<int:pk>/export/",                             views.export_visitors,               name="export"),
    # Public (no auth)
    path("sign-in/<uuid:token>/",                        views.sign_in_view,                 name="sign_in"),
]
