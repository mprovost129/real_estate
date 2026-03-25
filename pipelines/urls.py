from django.urls import path
from . import views

app_name = "pipelines"

urlpatterns = [
    path("", views.board_view, name="board"),
    path("<int:pipeline_pk>/", views.board_view, name="board_pipeline"),
    path("deals/add/", views.DealCreateView.as_view(), name="deal_create"),
    path("deals/<int:pk>/", views.DealDetailView.as_view(), name="deal_detail"),
    path("deals/<int:pk>/edit/", views.DealUpdateView.as_view(), name="deal_update"),
    path("deals/<int:pk>/move/", views.deal_move, name="deal_move"),
    path("deals/<int:pk>/delete/", views.deal_delete, name="deal_delete"),
]
