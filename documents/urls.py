
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("upload", views.upload, name="upload"),
    path("ask", views.ask, name="ask"),
    path("summarize", views.summarize, name="summarize"),
    path("health", views.health, name="health"),
]
