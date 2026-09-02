from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from events.models import CharityBagEvent


class Command(BaseCommand):
    help = "Create the configured Charity Bag instances for one competition day."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Competition date in YYYY-MM-DD; defaults to today.")

    def handle(self, *args, **options):
        try:
            event_date = (
                date.fromisoformat(options["date"]) if options["date"] else timezone.localdate()
            )
        except ValueError as exc:
            raise CommandError("--date must use YYYY-MM-DD.") from exc

        duration = timedelta(seconds=settings.CHARITY_BAG_DURATION_SECONDS)
        tz = timezone.get_current_timezone()
        created_count = 0
        for value in settings.CHARITY_BAG_SCHEDULE_TIMES:
            try:
                clock = time.fromisoformat(value)
            except ValueError as exc:
                raise CommandError(f"Invalid Charity Bag schedule time: {value}") from exc
            starts_at = timezone.make_aware(datetime.combine(event_date, clock), tz)
            _, created = CharityBagEvent.objects.get_or_create(
                starts_at=starts_at,
                defaults={"ends_at": starts_at + duration},
            )
            created_count += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Charity Bag schedule ready: {created_count} new instance(s), "
                f"{len(settings.CHARITY_BAG_SCHEDULE_TIMES)} configured."
            )
        )
