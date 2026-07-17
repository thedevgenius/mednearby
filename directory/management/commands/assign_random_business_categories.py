import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from directory.models import Business, Category


class Command(BaseCommand):
    help = "Assign a random active business category to each business."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible assignments.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing category assignments instead of preserving them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        categories = list(
            Category.objects.filter(
                type=Category.Type.BUSINESS_CATEGORY,
                is_active=True,
            ).order_by("display_order", "name")
        )
        if not categories:
            raise CommandError(
                "No active business categories exist. "
                "Run seed_directory_categories first."
            )

        rng = random.Random(options["seed"])
        overwrite = options["overwrite"]
        assigned = 0
        skipped = 0

        businesses = Business.objects.prefetch_related("categories").order_by("id")
        for business in businesses.iterator(chunk_size=200):
            if not overwrite and business.categories.exists():
                skipped += 1
                continue
            business.categories.set([rng.choice(categories)])
            assigned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned random categories to {assigned} businesses; "
                f"preserved {skipped} existing assignments."
            )
        )
