from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    # The inbox, always the caller's own — no user id in the URL to verify.
    path("notifications/", views.InboxView.as_view(), name="inbox"),
    path("notifications/read/", views.MarkReadView.as_view(), name="mark-read"),
    path(
        "notifications/<int:pk>/",
        views.NotificationDetailView.as_view(),
        name="notification-detail",
    ),
    path("notifications/read-all/", views.MarkAllReadView.as_view(), name="mark-all-read"),
    # The composer. Announcers only, all four.
    path("messages/", views.MessageListView.as_view(), name="message-list"),
    path("messages/audiences/", views.AudienceOptionsView.as_view(), name="message-audiences"),
    path(
        "messages/audience-preview/",
        views.AudiencePreviewView.as_view(),
        name="message-audience-preview",
    ),
    path("messages/<int:pk>/", views.MessageDetailView.as_view(), name="message-detail"),
    path("messages/<int:pk>/send/", views.MessageSendView.as_view(), name="message-send"),
    path(
        "messages/<int:pk>/recipients/",
        views.MessageRecipientsView.as_view(),
        name="message-recipients",
    ),
]
