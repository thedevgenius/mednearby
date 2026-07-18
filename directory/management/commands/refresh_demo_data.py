import itertools
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from directory.models import Business, Category, Doctor


BRANDS = (
    "Aarogya", "Apollo Care", "Carewell", "City Health", "Disha", "Greenlife",
    "Healthspring", "Lifeline", "MediTrust", "New Hope", "NovaCare", "Pulse",
    "Sanjeevani", "Shanti", "Sunrise", "Swasthya", "Wellcare", "Zenith",
    "Family First", "Health Point", "Niramaya", "Prana", "Seva", "VitaCare",
)
BUSINESS_KINDS = (
    "Clinic", "Medical Centre", "Health Centre", "Pharmacy", "Diagnostics",
    "Polyclinic", "Family Clinic", "Wellness Centre", "Care Centre",
    "Speciality Clinic", "Day Care Centre", "Medical Hub", "Health Studio",
)
ROADS = (
    "Lake Road", "Station Road", "MG Road", "Park Street", "College Road",
    "Hospital Road", "Central Avenue", "Market Road", "Temple Road", "Circular Road",
)
AREAS = (
    "New Town", "Salt Lake", "Ballygunge", "Behala", "Dum Dum", "Garia",
    "Tollygunge", "Jadavpur", "Howrah", "Kasba", "Rajarhat", "Barasat",
)
FIRST_NAMES = (
    "Aarav", "Aditi", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Meera",
    "Neha", "Rahul", "Riya", "Rohan", "Saanvi", "Vikram", "Vivaan", "Zoya",
    "Anirban", "Madhumita", "Sourav", "Priyanka", "Abhishek", "Nandini",
)
LAST_NAMES = (
    "Banerjee", "Basu", "Chatterjee", "Das", "Dutta", "Ghosh", "Gupta", "Iyer",
    "Kapoor", "Khan", "Mehta", "Mukherjee", "Nair", "Patel", "Rao", "Roy",
    "Sen", "Sharma", "Singh", "Verma", "Bose", "Chakraborty",
)
QUALIFICATIONS = (
    "MBBS, MD", "MBBS, DNB", "MBBS, MS", "MBBS, Diploma in Clinical Medicine",
    "MBBS, MD, Fellowship", "MBBS, MRCP", "BDS, MDS",
)
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def business_hours(rng):
    hours = {}
    for day in range(7):
        if day == 6 and rng.random() < 0.65:
            hours[str(day)] = []
        else:
            opens = rng.choice(("08:00", "09:00", "09:30", "10:00"))
            closes = rng.choice(("18:00", "19:00", "20:00", "21:00"))
            hours[str(day)] = [{"opens_at": opens, "closes_at": closes}]
    return hours


def doctor_schedule(rng):
    weekdays = sorted(rng.sample(range(7), rng.randint(3, 5)))
    split = rng.randint(2, len(weekdays) - 1)
    rules = []
    for days in (weekdays[:split], weekdays[split:]):
        start = rng.choice(("09:00", "10:00", "11:00", "16:00"))
        end = {"09:00": "13:00", "10:00": "14:00", "11:00": "15:00", "16:00": "20:00"}[start]
        rules.append({
            "weekdays": days,
            "slots": [{"start": start, "end": end}],
            "note": "Available every " + ", ".join(WEEKDAY_NAMES[day] for day in days),
        })
    return {"weekly": rules, "monthly_weekday": [], "monthly_dates": []}


class Command(BaseCommand):
    help = "Replace placeholder demo businesses and doctors with realistic development data."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=2026, help="Seed for repeatable output.")

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        businesses = list(
            Business.objects.filter(
                Q(address__istartswith="Dummy address") | Q(email__endswith="@demo.mednearby.in")
            ).order_by("id")
        )
        doctors = list(
            Doctor.objects.filter(
                Q(name__regex=r" [0-9]+$") | Q(business__email__endswith="@demo.mednearby.in")
            ).distinct().order_by("id")
        )
        if not businesses and not doctors:
            raise CommandError("No placeholder demo businesses or doctors were found.")

        categories = list(Category.objects.filter(type=Category.Type.BUSINESS_CATEGORY, is_active=True))
        specialties = list(Category.objects.filter(type=Category.Type.DOCTOR_SPECIALTY, is_active=True))
        if doctors and not specialties:
            raise CommandError("No active doctor specialties exist.")

        business_names = list(itertools.product(BRANDS, BUSINESS_KINDS))
        doctor_names = list(itertools.product(FIRST_NAMES, LAST_NAMES))
        rng.shuffle(business_names)
        rng.shuffle(doctor_names)
        if len(businesses) > len(business_names) or len(doctors) > len(doctor_names):
            raise CommandError("The realistic name pool is smaller than the demo dataset.")

        for index, (business, (brand, kind)) in enumerate(zip(businesses, business_names), start=1):
            area = rng.choice(AREAS)
            business.name = f"{brand} {kind}"
            business.address = f"{rng.randint(1, 249)}, {rng.choice(ROADS)}"
            business.landmark = f"Near {rng.choice(('City Mall', 'Metro Station', 'Community Park', 'Bus Stand', 'Central Market'))}"
            business.pincode = str(rng.randint(700001, 700159))
            business.phone = f"9{(100000000 + index):09d}"
            business.whatsapp = f"91{business.phone}"
            business.email = f"care{index}@demo.mednearby.in"
            business.description = (
                f"{business.name} provides dependable healthcare services for families in {area}, "
                "with experienced staff, modern facilities and patient-friendly support."
            )
            business.business_hours = business_hours(rng)
            business.services = rng.sample(
                ["Doctor consultation", "Health check-up", "Medicine support", "Home service", "Diagnostic tests", "Follow-up care"],
                3,
            )
            business.established_year = rng.randint(2004, 2022)
            business.verification_status = Business.VerificationStatus.VERIFIED
            business.publication_status = Business.PublicationStatus.PUBLISHED
            business.is_active = True
            business.save()
            if categories:
                business.categories.set(rng.sample(categories, min(rng.randint(1, 2), len(categories))))

        available_businesses = businesses or list(Business.objects.filter(is_active=True))
        for index, (doctor, (first_name, last_name)) in enumerate(zip(doctors, doctor_names), start=1):
            doctor.name = f"Dr. {first_name} {last_name}"
            doctor.slug = ""
            doctor.business = doctor.business if doctor.business in available_businesses else rng.choice(available_businesses)
            doctor.qualification = rng.choice(QUALIFICATIONS)
            doctor.gender = rng.choice((Doctor.GenderChoices.MALE, Doctor.GenderChoices.FEMALE))
            doctor.fees = str(rng.choice(range(400, 1300, 100)))
            doctor.bio = (
                f"Dr. {first_name} {last_name} is a compassionate clinician with extensive experience "
                "in evidence-based diagnosis, treatment and preventive care."
            )
            doctor.schedule = doctor_schedule(rng)
            doctor.is_active = True
            doctor.is_featured = index <= max(8, len(doctors) // 12)
            doctor.save()
            doctor.specialties.set(rng.sample(specialties, min(rng.randint(1, 2), len(specialties))))

        self.stdout.write(self.style.SUCCESS(
            f"Refreshed {len(businesses)} demo businesses and {len(doctors)} demo doctors."
        ))
