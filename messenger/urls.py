from django.urls import path
from . import views

app_name = "messenger"
urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("n8n-webhook/", views.n8n_webhook, name="n8n_webhook"),
    path("ai/context/", views.ai_context, name="ai_context"),
    path("ai/services/", views.ai_services, name="ai_services"),
    path("ai/availability/", views.ai_availability, name="ai_availability"),
    path("ai/book/", views.ai_book, name="ai_book"),
]
