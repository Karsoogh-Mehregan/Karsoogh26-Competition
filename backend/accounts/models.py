from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    team = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="members",
    )
