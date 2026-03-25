from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("",                        views.TaskListView.as_view(),   name="list"),
    path("new/",                    views.TaskCreateView.as_view(), name="create"),
    path("<int:pk>/",               views.TaskDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/",          views.TaskUpdateView.as_view(), name="update"),
    path("<int:pk>/complete/",      views.task_complete,            name="complete"),
    path("<int:pk>/snooze/",        views.task_snooze,              name="snooze"),
    path("<int:pk>/delete/",        views.task_delete,              name="delete"),
]
