import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from directory.models import Ambulance, Business


class Command(BaseCommand):
    help = "Create dummy ambulances and assign them to existing active businesses."

    def add_arguments(self, parser):
        parser.add_argument(
            "count",
            type=int,
            nargs="?",
            default=50,
            help="Number of ambulances to create (default: 50)",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible data",
        )

    @staticmethod
    def unique_phone(rng, used_phones):
        while True:
            phone = f"{rng.choice('6789')}{rng.randrange(10**9):09d}"
            if phone not in used_phones:
                used_phones.add(phone)
                return phone

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        if count < 1:
            raise CommandError("count must be at least 1")

        businesses = list(
            Business.objects.filter(is_active=True, is_testing=False).only(
                "id", "name"
            )
        )
        if not businesses:
            raise CommandError("No active non-testing businesses exist")

        rng = random.Random(options["seed"])
        used_phones = set(Ambulance.objects.values_list("phone", flat=True))
        ambulances = [
            Ambulance(
                business=rng.choice(businesses),
                phone=self.unique_phone(rng, used_phones),
                is_active=True,
                is_24_7=rng.random() < 0.7,
            )
            for _ in range(count)
        ]
        Ambulance.objects.bulk_create(ambulances, batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {count} dummy ambulances using "
                f"{len(businesses)} active businesses."
            )
        )
