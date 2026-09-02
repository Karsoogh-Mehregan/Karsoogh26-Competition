from django.core.management.base import BaseCommand

from events.services import sync_due_charity_bags


class Command(BaseCommand):
    help = "Activate scheduled Charity Bags and idempotently settle expired instances."

    def handle(self, *args, **options):
        sync_due_charity_bags()
        self.stdout.write(self.style.SUCCESS("Charity Bag states are up to date."))
