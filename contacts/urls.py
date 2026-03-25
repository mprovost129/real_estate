from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("", views.ContactListView.as_view(), name="list"),
    path("add/", views.ContactCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ContactDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ContactUpdateView.as_view(), name="update"),
    path("<int:pk>/note/", views.contact_add_note, name="add_note"),
    path("<int:pk>/log/",       views.log_communication,  name="log_communication"),
    path("<int:pk>/quick-task/",views.contact_quick_task,  name="quick_task"),
    path("<int:pk>/documents/upload/", views.contact_document_upload, name="document_upload"),
    path("<int:pk>/documents/<int:doc_pk>/delete/", views.contact_document_delete, name="document_delete"),
    path("<int:pk>/delete/",    views.contact_delete,      name="delete"),
    path("import/",              views.contact_import,      name="import"),
    path("export/",              views.contact_export,      name="export"),
    path("follow-up/",           views.follow_up_center,    name="follow_up"),
    path("follow-up/reminders/", views.generate_reminders,  name="generate_reminders"),
    path("tags/",                views.tag_list,             name="tag_list"),
    path("tags/<int:pk>/edit/",  views.tag_edit,             name="tag_edit"),
    path("tags/<int:pk>/delete/",views.tag_delete,           name="tag_delete"),
    path("<int:pk>/tags/",       views.contact_set_tags,     name="set_tags"),
]
