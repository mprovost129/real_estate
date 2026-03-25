from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("",                                            views.TransactionListView.as_view(),   name="list"),
    path("new/",                                        views.TransactionCreateView.as_view(),  name="create"),
    path("<int:pk>/",                                   views.TransactionDetailView.as_view(),  name="detail"),
    path("<int:pk>/edit/",                              views.TransactionUpdateView.as_view(),  name="update"),
    path("<int:pk>/delete/",                            views.transaction_delete,               name="delete"),
    path("<int:pk>/notes/add/",                         views.add_note,                         name="add_note"),
    path("<int:pk>/checklist/<int:item_pk>/toggle/",    views.checklist_toggle,                 name="checklist_toggle"),
    path("<int:pk>/checklist/<int:item_pk>/update/",    views.checklist_item_update,            name="checklist_item_update"),
    path("<int:pk>/documents/upload/",                 views.document_upload,                  name="document_upload"),
    path("<int:pk>/documents/<int:doc_pk>/delete/",    views.document_delete,                  name="document_delete"),
]
