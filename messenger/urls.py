from django.urls import path
from . import views

app_name = "messenger"
urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("n8n-webhook/", views.n8n_webhook, name="n8n_webhook"),
    path("meta/verify-signature/", views.meta_signature_verify, name="meta_signature_verify"),
    path("ai/context/", views.ai_context, name="ai_context"),
    path("ai/services/", views.ai_services, name="ai_services"),
    path("ai/availability/", views.ai_availability, name="ai_availability"),
    path("ai/book/", views.ai_book, name="ai_book"),
    path("ai/appointment/lookup/", views.ai_appointment_lookup, name="ai_appointment_lookup"),
    path("ai/appointment/cancel/", views.ai_appointment_cancel, name="ai_appointment_cancel"),
    path("ai/appointment/reschedule/", views.ai_appointment_reschedule, name="ai_appointment_reschedule"),
    path("ai/widget/context/", views.widget_ai_context, name="widget_ai_context"),
    path("ai/widget/services/", views.widget_ai_services, name="widget_ai_services"),
    path("ai/widget/availability/", views.widget_ai_availability, name="widget_ai_availability"),
    path("ai/widget/book/", views.widget_ai_book, name="widget_ai_book"),
    path("ai/widget/appointment/lookup/", views.widget_ai_appointment_lookup, name="widget_ai_appointment_lookup"),
    path("ai/widget/appointment/cancel/", views.widget_ai_appointment_cancel, name="widget_ai_appointment_cancel"),
    path("ai/widget/appointment/reschedule/", views.widget_ai_appointment_reschedule, name="widget_ai_appointment_reschedule"),
]
