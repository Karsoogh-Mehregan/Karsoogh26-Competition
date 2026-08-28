"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.api_urls")),
]
