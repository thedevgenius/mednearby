import random

from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import Business


def generate_weekly_hours(rng):
    """Return a seven-day schedule using string weekday keys (Monday = 0)."""
    schedule = {}
    for weekday in range(7):
        closed_chance = 0.35 if weekday == 6 else 0.05
        if rng.random() < closed_chance:
            schedule[str(weekday)] = []
            continue

        opens_hour = rng.choice((8, 9, 10))
        closes_hour = rng.choice((17, 18, 19, 20))
        if weekday == 5:
            closes_hour = rng.choice((15, 16, 17, 18))

        if rng.random() < 0.25 and closes_hour >= 18:
            first_close = rng.choice((13, 14, 15))
            second_open = rng.choice((16, 17, 18))
            second_close = max(second_open + 2, closes_hour)
            schedule[str(weekday)] = [
                {
                    "opens_at": f"{opens_hour:02d}:00",
                    "closes_at": f"{first_close:02d}:00",
                },
                {
                    "opens_at": f"{second_open:02d}:00",
                    "closes_at": f"{second_close:02d}:00",
                },
            ]
        else:
            schedule[str(weekday)] = [
                {
                    "opens_at": f"{opens_hour:02d}:00",
                    "closes_at": f"{closes_hour:02d}:00",
                }
            ]
    return schedule


class Command(BaseCommand):
    help = "Add random weekly business-hours JSON to every business."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible schedules",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace schedules that already contain business hours",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        overwrite = options["overwrite"]
        businesses = []
        skipped = 0

        for business in Business.objects.only("id", "business_hours").iterator():
            if business.business_hours and not overwrite:
                skipped += 1
                continue
            business.business_hours = generate_weekly_hours(rng)
            businesses.append(business)

        if businesses:
            Business.objects.bulk_update(
                businesses,
                ["business_hours"],
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Added random business hours to {len(businesses)} businesses; "
                f"skipped {skipped} existing schedules."
            )
        )
