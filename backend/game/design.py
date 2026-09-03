"""The vocabulary the map's look is described in.

Keep this file in step with the frontend: `frontend/src/lib/house/archetypes.ts`
owns what each building *looks like* and `frontend/src/lib/house/themes.ts` owns
each neighbourhood's palette. This module only names them, so the admin dropdown
and the API validator agree with the renderer about which keys exist.
"""

from django.db import models

# Building types a Designer may pin to a node. The renderer picks one of these
# by itself for every node it has no pin for, choosing so that no two adjacent
# nodes share a type.
ARCHETYPES = [
    ("mint", "ضراب‌خانه"),
    ("cityhall", "شهرداری"),
    ("bakery", "نانوایی"),
    ("restaurant", "رستوران"),
    ("school", "مدرسه"),
    ("icecream", "بستنی‌فروشی"),
    ("newspaper", "روزنامهٔ گیل‌بهشت"),
    ("hotel", "مهمان‌سرا"),
    ("caravanserai", "کاروانسرا"),
    ("stadium", "زمین چولیگان"),
    ("farm", "زمین کشاورزی"),
    ("guardpost", "نگهبانی دیوار"),
    ("observatory", "رصدخانه"),
    ("grocery", "بقالی"),
    ("dairy", "گاوداری"),
    ("stable", "اسب‌داری"),
    ("hospital", "شفاخانه"),
    ("courthouse", "دادسرا"),
    ("ministry", "وزارتخانه"),
    ("mine", "معدن"),
    ("trade", "تجارت‌خانه"),
    ("industry", "کارخانه"),
    ("sawmill", "کارگاه چوب‌بری"),
    ("tailor", "کارگاه لباس‌دوزی"),
    ("smithy", "کارگاه آهنگری"),
    ("library", "کتابخانه"),
]

ARCHETYPE_KEYS = frozenset(key for key, _ in ARCHETYPES)


class NeighborhoodTheme(models.TextChoices):
    WATER = "water", "آبی — آب"
    FIRE = "fire", "قرمز — آتش"
    LIGHTNING = "lightning", "نارنجی — رعد و برق"
    HISTORY = "history", "سبز — باستان‌شناسی"
    SPORT = "sport", "زرد — ورزش"
    KNOWLEDGE = "knowledge", "بنفش — دانش"
    UNBUILT = "unbuilt", "سفید — نیمه‌ساخته"
    TRIBAL = "tribal", "خاکستری — قبیله‌ای"
    SOIL = "soil", "قهوه‌ای — خاک"


class RoadStyle(models.TextChoices):
    STRAIGHT = "straight", "مستقیم"
    CURVED = "curved", "منحنی"
    DASHED = "dashed", "خط‌چین"


# The map has eight 45° sectors; nine themes are on offer, so one sits out by
# default (the unbuilt one — it is the theme *for* not having an identity yet).
SECTOR_COUNT = 8

DEFAULT_NEIGHBORHOODS = [
    (0, "محلهٔ آبی", NeighborhoodTheme.WATER, "#3b82c4"),
    (1, "محلهٔ قرمز", NeighborhoodTheme.FIRE, "#c8402f"),
    (2, "محلهٔ نارنجی", NeighborhoodTheme.LIGHTNING, "#e08a2a"),
    (3, "محلهٔ سبز", NeighborhoodTheme.HISTORY, "#5f8f4e"),
    (4, "محلهٔ زرد", NeighborhoodTheme.SPORT, "#d9b83a"),
    (5, "محلهٔ بنفش", NeighborhoodTheme.KNOWLEDGE, "#7b5ea7"),
    (6, "محلهٔ خاکستری", NeighborhoodTheme.TRIBAL, "#6f6f78"),
    (7, "محلهٔ قهوه‌ای", NeighborhoodTheme.SOIL, "#8a6242"),
]
