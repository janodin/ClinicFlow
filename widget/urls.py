from django.urls import path

from . import views

app_name = "widget"

urlpatterns = [
    path("<slug:clinic_slug>/", views.widget_home, name="home"),
    path("<slug:clinic_slug>/book/", views.widget_book, name="book"),
    path("<slug:clinic_slug>/slots/", views.widget_slots, name="slots"),
    path("<slug:clinic_slug>/embed.js", views.embed_js, name="embed_js"),
    path("<slug:clinic_slug>/chat/", views.chat_api, name="chat_api"),
    path("<slug:clinic_slug>/chat/step/", views.chat_step, name="chat_step"),
]
