from django.urls import path
from . import views

app_name = "messenger"
urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("n8n-webhook/", views.n8n_webhook, name="n8n_webhook"),
]
