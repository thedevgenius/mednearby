import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from directory.models import Business, BusinessUpdate


UPDATE_TEMPLATES = (
    (
        BusinessUpdate.Kind.ANNOUNCEMENT,
        "Extended clinic hours",
        "We are extending our consultation hours for patient convenience.",
        "The clinic will remain open later on weekdays. Please call the reception desk to confirm the latest appointment slots.",
    ),
    (
        BusinessUpdate.Kind.OFFER,
        "Complimentary health check",
        "Get a complimentary basic health check for a limited time.",
        "The health check includes blood pressure, pulse, BMI, and a brief consultation. Terms and availability may apply.",
    ),
    (
        BusinessUpdate.Kind.DOCTOR_AVAILABILITY,
        "Doctor unavailable today",
        "One of our doctors will be unavailable for consultations today.",
        "Patients with existing appointments will be contacted by the clinic. Please call us to reschedule or ask about another available doctor.",
    ),
    (
        BusinessUpdate.Kind.NEW_DOCTOR,
        "New doctor joining our team",
        "A new experienced doctor is now available for consultations.",
        "Appointments are now open. Contact the clinic for the doctor's specialty, consultation schedule, and fees.",
    ),
    (
        BusinessUpdate.Kind.ANNOUNCEMENT,
        "Weekend appointment slots available",
        "Additional appointment slots are available this weekend.",
        "Advance booking is recommended because weekend availability is limited. Contact the clinic to reserve a convenient time.",
    ),
)


class Command(BaseCommand):
    help = "Add repeatable dummy updates and offers to published businesses."

    def add_arguments(self, parser):
        parser.add_argument(
            "count",
            nargs="?",
            type=int,
            default=3,
            help="Number of updates to create per business (default: 3).",
        )
        parser.add_argument("--seed", type=int, default=2026, help="Seed for repeatable output.")
        parser.add_argument(
            "--business-slug",
            help="Create updates only for the published business with this slug.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        if count < 1:
            raise CommandError("count must be at least 1.")

        businesses = Business.objects.filter(
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
        ).order_by("id")
        if options["business_slug"]:
            businesses = businesses.filter(slug=options["business_slug"])
        businesses = list(businesses)
        if not businesses:
            raise CommandError("No matching active, published businesses were found.")

        rng = random.Random(options["seed"])
        now = timezone.now()
        created_count = 0
        existing_count = 0
        for business in businesses:
            templates = list(UPDATE_TEMPLATES)
            rng.shuffle(templates)
            for number in range(count):
                kind, base_title, summary, details = templates[number % len(templates)]
                cycle = number // len(templates)
                title = base_title if cycle == 0 else f"{base_title} ({cycle + 1})"
                defaults = {
                    "kind": kind,
                    "summary": summary,
                    "details": details,
                    "starts_at": now,
                    "ends_at": now + timedelta(days=30) if kind == BusinessUpdate.Kind.OFFER else None,
                    "is_published": True,
                }
                _, created = BusinessUpdate.objects.get_or_create(
                    business=business,
                    title=title,
                    defaults=defaults,
                )
                created_count += int(created)
                existing_count += int(not created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Dummy updates complete: {created_count} created, "
                f"{existing_count} already existed across {len(businesses)} business(es)."
            )
        )
