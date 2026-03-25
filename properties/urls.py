from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("",              views.PropertyListView.as_view(),   name="list"),
    path("new/",          views.PropertyCreateView.as_view(), name="create"),
    path("<int:pk>/",     views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/",     views.PropertyUpdateView.as_view(), name="update"),
    path("<int:pk>/note/",                               views.property_add_note,    name="add_note"),
    path("<int:pk>/delete/",                             views.property_delete,      name="delete"),
    path("<int:pk>/photos/upload/",                      views.photo_upload,         name="photo_upload"),
    path("<int:pk>/photos/<int:photo_pk>/delete/",       views.photo_delete,         name="photo_delete"),
    path("<int:pk>/photos/<int:photo_pk>/set-primary/",  views.photo_set_primary,    name="photo_set_primary"),
    path("<int:pk>/photos/<int:photo_pk>/caption/",      views.photo_caption,        name="photo_caption"),
]
