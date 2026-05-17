from django.urls import path

from . import views

app_name = "public_booking"

urlpatterns = [
    path("<slug:clinic_slug>/book/", views.public_booking, name="book"),
]
