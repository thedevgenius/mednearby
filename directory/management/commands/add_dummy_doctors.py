import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from directory.models import Business, Category, Doctor


FIRST_NAMES = (
    "Aarav",
    "Ananya",
    "Arjun",
    "Diya",
    "Ishaan",
    "Kavya",
    "Meera",
    "Neha",
    "Rahul",
    "Riya",
    "Rohan",
    "Saanvi",
    "Vikram",
    "Vivaan",
)
LAST_NAMES = (
    "Banerjee",
    "Chatterjee",
    "Das",
    "Gupta",
    "Iyer",
    "Kapoor",
    "Khan",
    "Mehta",
    "Mukherjee",
    "Patel",
    "Rao",
    "Sen",
    "Sharma",
    "Singh",
)
QUALIFICATIONS = (
    "MBBS",
    "MBBS, MD",
    "MBBS, MS",
    "MBBS, DNB",
    "MBBS, Diploma in Clinical Medicine",
)


class Command(BaseCommand):
    help = "Create dummy doctors using existing doctor specialties and businesses."

    def add_arguments(self, parser):
        parser.add_argument(
            "count",
            type=int,
            nargs="?",
            default=200,
            help="Number of doctors to create (default: 200)",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible data",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        if count < 1:
            raise CommandError("count must be at least 1")

        specialties = list(
            Category.objects.filter(
                type=Category.Type.DOCTOR_SPECIALTY,
                is_active=True,
            )
        )
        if not specialties:
            raise CommandError("No active doctor specialties exist")

        businesses = list(Business.objects.filter(is_active=True))
        rng = random.Random(options["seed"])

        for number in range(1, count + 1):
            first_name = rng.choice(FIRST_NAMES)
            last_name = rng.choice(LAST_NAMES)
            doctor = Doctor.objects.create(
                name=f"Dr. {first_name} {last_name} {number}",
                business=rng.choice(businesses) if businesses else None,
                qualification=rng.choice(QUALIFICATIONS),
                bio=(
                    f"Dr. {first_name} {last_name} is an experienced medical "
                    "professional committed to patient-focused care."
                ),
                is_active=True,
                is_featured=rng.random() < 0.1,
            )
            specialty_count = rng.randint(1, min(3, len(specialties)))
            doctor.specialties.set(rng.sample(specialties, specialty_count))

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {count} dummy doctors using "
                f"{len(specialties)} existing specialties."
            )
        )
