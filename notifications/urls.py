from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("",                        views.notification_list,    name="list"),
    path("<int:pk>/read/",          views.mark_read,            name="mark_read"),
    path("<int:pk>/delete/",        views.delete_notification,  name="delete"),
    path("mark-all-read/",          views.mark_all_read,        name="mark_all_read"),
    path("api/unread-count/",       views.unread_count_api,     name="unread_count_api"),
]
