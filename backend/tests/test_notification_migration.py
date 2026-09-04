import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_retiring_system_fields_preserves_messages_and_read_receipts():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("notifications", "0005_drop_single_audience")]
    try:
        executor.migrate(previous)
        old_apps = executor.loader.project_state(previous).apps
        User = old_apps.get_model("accounts", "User")
        Message = old_apps.get_model("notifications", "Message")
        Notification = old_apps.get_model("notifications", "Notification")
        user = User.objects.create(username="migration-reader")
        now = timezone.now()
        message = Message.objects.create(
            kind="system",
            status="sent",
            sent_at=now,
            sender_label="Game",
            title="Historical result",
            body="Keep this result",
        )
        receipt = Notification.objects.create(message=message, user=user, read_at=now)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        new_apps = executor.loader.project_state(latest).apps
        saved = new_apps.get_model("notifications", "Message").objects.get(pk=message.pk)
        saved_receipt = new_apps.get_model("notifications", "Notification").objects.get(
            pk=receipt.pk
        )
        assert saved.body == "Keep this result"
        assert saved.sender_label == "Game"
        assert saved_receipt.message_id == message.pk
        assert saved_receipt.read_at == now
    finally:
        MigrationExecutor(connection).migrate(latest)
