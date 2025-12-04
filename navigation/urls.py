# navigation/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('toggle-theme/', views.toggle_theme_view, name='toggle_theme'),
]