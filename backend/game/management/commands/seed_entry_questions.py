"""Seed a starter pool of Persian entry-sheet questions.

A management command rather than a data migration: these are sample questions
for organisers to replace in admin, and forcing them onto every deployment is
not the migration's job. Idempotent — re-running never overwrites edits.

    uv run manage.py seed_entry_questions
    uv run manage.py seed_entry_questions --overwrite   # push the text back
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from game.models import EntryQuestion

# Short, integer-answered, and easy on purpose: the sheet is a gate, not a
# ranking. `answer` is what teams are checked against and is never serialised.
QUESTIONS = [
    {
        "code": "entry-sum-1-10",
        "title": "جمع یک تا ده",
        "body": "حاصل جمع همهٔ عددهای صحیح از ۱ تا ۱۰ چند است؟",
        "answer": 55,
    },
    {
        "code": "entry-perimeter",
        "title": "محیط مستطیل",
        "body": "مستطیلی به طول ۱۲ و عرض ۷ داریم. محیط این مستطیل چند است؟",
        "answer": 38,
    },
    {
        "code": "entry-glasses",
        "title": "عینک در کلاس",
        "body": ("در کلاسی ۳۰ نفره، دو سوم دانش‌آموزان عینک دارند. چند دانش‌آموز عینک ندارند؟"),
        "answer": 10,
    },
    {
        "code": "entry-power-two",
        "title": "توان دو",
        "body": "عدد ۲ به توان ۱۰ چند می‌شود؟",
        "answer": 1024,
    },
    {
        "code": "entry-primes",
        "title": "عددهای اول",
        "body": "چند عدد اولِ دورقمیِ کوچک‌تر از ۳۰ وجود دارد؟",
        "answer": 6,
    },
    {
        "code": "entry-clock-angle",
        "title": "زاویهٔ عقربه‌ها",
        "body": ("ساعت دقیقاً ۳:۰۰ است. زاویهٔ بین عقربهٔ ساعت‌شمار و دقیقه‌شمار چند درجه است؟"),
        "answer": 90,
    },
    {
        "code": "entry-workers",
        "title": "کارگرها و دستگاه‌ها",
        "body": (
            "اگر ۵ کارگر بتوانند ۵ دستگاه را در ۵ روز بسازند، "
            "۱۰۰ کارگر ۱۰۰ دستگاه را در چند روز می‌سازند؟"
        ),
        "answer": 5,
    },
    {
        "code": "entry-handshakes",
        "title": "دست دادن",
        "body": "در جمعی ۶ نفره هر دو نفر یک بار با هم دست می‌دهند. مجموعاً چند دست دادن رخ می‌دهد؟",
        "answer": 15,
    },
]


class Command(BaseCommand):
    help = "Create the sample Persian entry-sheet questions (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Reset title/body/answer of questions that already exist.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = unchanged = 0

        for spec in QUESTIONS:
            question, was_created = EntryQuestion.objects.get_or_create(
                code=spec["code"],
                defaults={
                    "title": spec["title"],
                    "body": spec["body"],
                    "answer": spec["answer"],
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            elif options["overwrite"]:
                question.title = spec["title"]
                question.body = spec["body"]
                question.answer = spec["answer"]
                question.save(update_fields=["title", "body", "answer"])
                updated += 1
            else:
                unchanged += 1

        if options["verbosity"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Entry questions: {created} created, {updated} updated, "
                    f"{unchanged} unchanged "
                    f"({EntryQuestion.objects.filter(is_active=True).count()} active)."
                )
            )
