from django.urls import path
from . import views

app_name = "messenger"
urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
]
