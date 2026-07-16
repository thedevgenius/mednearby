import random

from django.core.management.base import BaseCommand
from django.db import transaction

from directory.models import Doctor


class Command(BaseCommand):
    help = "Add random consultation fees to every doctor."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible fees",
        )
        parser.add_argument(
            "--min-fee",
            type=int,
            default=300,
            help="Minimum fee in rupees (default: 300)",
        )
        parser.add_argument(
            "--max-fee",
            type=int,
            default=2000,
            help="Maximum fee in rupees (default: 2000)",
        )
        parser.add_argument(
            "--step",
            type=int,
            default=100,
            help="Fee increment in rupees (default: 100)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace fees that are already set",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        minimum = options["min_fee"]
        maximum = options["max_fee"]
        step = options["step"]
        if minimum < 0 or maximum < minimum or step < 1:
            self.stderr.write(
                self.style.ERROR(
                    "Fees require min-fee >= 0, max-fee >= min-fee, and step >= 1."
                )
            )
            return

        fee_choices = list(range(minimum, maximum + 1, step))
        rng = random.Random(options["seed"])
        doctors = []
        skipped = 0

        for doctor in Doctor.objects.only("id", "fees").iterator():
            if doctor.fees and not options["overwrite"]:
                skipped += 1
                continue
            doctor.fees = str(rng.choice(fee_choices))
            doctors.append(doctor)

        if doctors:
            Doctor.objects.bulk_update(doctors, ["fees"], batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(
                f"Added random fees to {len(doctors)} doctors; "
                f"skipped {skipped} existing fees."
            )
        )
