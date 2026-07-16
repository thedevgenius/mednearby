import random

from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import Doctor


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def generate_slots(rng):
    start_hour = rng.choice((8, 9, 10, 11))
    first_end = rng.choice((13, 14, 15))
    slots = [{"start": f"{start_hour:02d}:00", "end": f"{first_end:02d}:00"}]
    if rng.random() < 0.4:
        evening_start = rng.choice((16, 17, 18))
        evening_end = rng.choice(tuple(range(evening_start + 2, 22)))
        slots.append(
            {
                "start": f"{evening_start:02d}:00",
                "end": f"{evening_end:02d}:00",
            }
        )
    return slots


def weekday_label(weekdays):
    return ", ".join(WEEKDAY_NAMES[weekday] for weekday in weekdays)


def generate_doctor_schedule(rng):
    weekdays = list(range(7))
    rng.shuffle(weekdays)
    weekly = []
    for weekday_group in (sorted(weekdays[:3]), sorted(weekdays[3:5])):
        weekly.append(
            {
                "weekdays": weekday_group,
                "slots": generate_slots(rng),
                "note": f"Available every {weekday_label(weekday_group)}",
            }
        )

    monthly_weekday = []
    if rng.random() < 0.6:
        selected_weekdays = sorted(rng.sample(range(7), rng.randint(1, 2)))
        week_numbers = sorted(
            rng.sample((1, 2, 3, 4, -1), rng.randint(1, 2)),
            key=lambda number: 5 if number == -1 else number,
        )
        monthly_weekday.append(
            {
                "weekdays": selected_weekdays,
                "week_numbers": week_numbers,
                "slots": generate_slots(rng),
                "note": f"Selected monthly {weekday_label(selected_weekdays)} consultations",
            }
        )

    monthly_dates = []
    if rng.random() < 0.6:
        dates = sorted(rng.sample(range(1, 29), rng.randint(1, 4)))
        monthly_dates.append(
            {
                "dates": dates,
                "slots": generate_slots(rng),
                "note": "Available on selected dates every month",
            }
        )

    return {
        "weekly": weekly,
        "monthly_weekday": monthly_weekday,
        "monthly_dates": monthly_dates,
    }


class Command(BaseCommand):
    help = "Add random schedule JSON to every doctor."

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
            help="Replace schedules that already contain data",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        doctors = []
        skipped = 0

        for doctor in Doctor.objects.only("id", "schedule").iterator():
            if doctor.schedule and not options["overwrite"]:
                skipped += 1
                continue
            doctor.schedule = generate_doctor_schedule(rng)
            doctors.append(doctor)

        if doctors:
            Doctor.objects.bulk_update(doctors, ["schedule"], batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(
                f"Added random schedules to {len(doctors)} doctors; "
                f"skipped {skipped} existing schedules."
            )
        )
