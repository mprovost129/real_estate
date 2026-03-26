from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("search/",   views.global_search, name="global_search"),
    path("calendar/", views.calendar_view, name="calendar"),

    # Password reset
    path("password/reset/", views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),

    # Password change (logged in)
    path("password/change/", views.CustomPasswordChangeView.as_view(), name="password_change"),
    path("password/change/done/", views.CustomPasswordChangeDoneView.as_view(), name="password_change_done"),
    path("settings/public-page/", views.public_page_settings, name="public_page_settings"),
    path("public/agents/<slug:slug>/", views.public_agent_page, name="public_agent_page"),
]
