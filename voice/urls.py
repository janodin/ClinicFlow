from django.urls import path

from . import views

app_name = "voice"

urlpatterns = [
    path("provider/webhook/", views.provider_webhook, name="provider_webhook"),
    path("widget/<slug:clinic_slug>/session/", views.widget_session, name="widget_session"),
    path("widget/<slug:clinic_slug>/session/<str:public_session_id>/turn/", views.widget_turn, name="widget_turn"),
    path("widget/<slug:clinic_slug>/session/<str:public_session_id>/end/", views.widget_end, name="widget_end"),
    path("dashboard/test/session/", views.dashboard_test_session, name="dashboard_test_session"),
    path("dashboard/test/session/<str:public_session_id>/turn/", views.dashboard_test_turn, name="dashboard_test_turn"),
    path("dashboard/test/session/<str:public_session_id>/end/", views.dashboard_test_end, name="dashboard_test_end"),
]
