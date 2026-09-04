from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0021_item_floors_may_stack"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="answer_type",
            field=models.CharField(
                choices=[("text", "متن"), ("file", "فایل"), ("numeric", "عددی")],
                default="file",
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="question",
            name="body",
            field=models.TextField(blank=True, help_text="Markdown"),
        ),
    ]
