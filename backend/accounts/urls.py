from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="csrf"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
]
