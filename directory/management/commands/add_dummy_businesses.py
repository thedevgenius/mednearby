import math
import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from directory.models import Business


EARTH_RADIUS_KM = 6371.0088
BUSINESS_PREFIXES = (
    "Aarogya",
    "CarePoint",
    "HealthFirst",
    "MediCare",
    "Wellness",
    "LifeLine",
    "CityCare",
    "GoodHealth",
)
BUSINESS_SUFFIXES = (
    "Clinic",
    "Pharmacy",
    "Diagnostics",
    "Healthcare",
    "Medical Centre",
    "Wellness Centre",
)


def random_coordinate(center_latitude, center_longitude, radius_km, rng):
    """Return a point distributed uniformly by area inside a geographic circle."""
    distance = radius_km * math.sqrt(rng.random())
    bearing = rng.uniform(0, 2 * math.pi)
    angular_distance = distance / EARTH_RADIUS_KM
    latitude_1 = math.radians(center_latitude)
    longitude_1 = math.radians(center_longitude)

    latitude_2 = math.asin(
        math.sin(latitude_1) * math.cos(angular_distance)
        + math.cos(latitude_1) * math.sin(angular_distance) * math.cos(bearing)
    )
    longitude_2 = longitude_1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(latitude_1),
        math.cos(angular_distance) - math.sin(latitude_1) * math.sin(latitude_2),
    )

    latitude = math.degrees(latitude_2)
    longitude = (math.degrees(longitude_2) + 540) % 360 - 180
    return latitude, longitude


class Command(BaseCommand):
    help = "Create dummy businesses randomly distributed within a radius."

    def add_arguments(self, parser):
        parser.add_argument("count", type=int, help="Number of businesses to create")
        parser.add_argument("center_lat", type=float, help="Circle center latitude")
        parser.add_argument("center_lng", type=float, help="Circle center longitude")
        parser.add_argument("radius_km", type=float, help="Circle radius in kilometres")
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for reproducible data",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        center_latitude = options["center_lat"]
        center_longitude = options["center_lng"]
        radius_km = options["radius_km"]

        if count < 1:
            raise CommandError("count must be at least 1")
        if not -90 <= center_latitude <= 90:
            raise CommandError("center_lat must be between -90 and 90")
        if not -180 <= center_longitude <= 180:
            raise CommandError("center_lng must be between -180 and 180")
        if radius_km < 0:
            raise CommandError("radius_km cannot be negative")

        rng = random.Random(options["seed"])
        coordinate_precision = Decimal("0.000000001")

        for number in range(1, count + 1):
            latitude, longitude = random_coordinate(
                center_latitude,
                center_longitude,
                radius_km,
                rng,
            )
            prefix = rng.choice(BUSINESS_PREFIXES)
            suffix = rng.choice(BUSINESS_SUFFIXES)
            business = Business(
                name=f"{prefix} {suffix} {number}",
                address=f"Dummy address {number}",
                latitude=Decimal(str(latitude)).quantize(coordinate_precision),
                longitude=Decimal(str(longitude)).quantize(coordinate_precision),
                is_active=True,
                publication_status=Business.PublicationStatus.PUBLISHED,
                verification_status=Business.VerificationStatus.VERIFIED,
            )
            business.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {count} dummy businesses within {radius_km:g} km "
                f"of ({center_latitude:g}, {center_longitude:g})."
            )
        )
