import math
import random
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from directory.models import (
    Ambulance,
    Business,
    BusinessImage,
    BusinessUpdate,
    Category,
    Doctor,
    Facility,
    Lead,
)
from locations.models import City, Locality, State


BRANDS = (
    "Aarogya", "CarePoint", "HealthFirst", "MediTrust", "Sanjeevani",
    "Wellcare", "CityLife", "NovaCare", "Healthspring", "Lifeline",
    "Swasthya", "Apollo", "Greenlife", "Niramaya", "Pulse",
    "Family First", "Prana", "Sunrise", "VitaCare", "Zenith",
)
FIRST_NAMES = (
    "Aditi", "Arjun", "Ananya", "Rahul", "Meera", "Vikram", "Neha",
    "Rohan", "Kavya", "Ishaan", "Nandini", "Sourav", "Priyanka",
    "Abhishek", "Riya", "Anirban", "Madhumita", "Vivaan", "Zoya", "Diya",
)
LAST_NAMES = (
    "Banerjee", "Basu", "Chatterjee", "Das", "Dutta", "Ghosh", "Gupta",
    "Kapoor", "Khan", "Mukherjee", "Nair", "Patel", "Roy", "Sen",
    "Sharma", "Singh", "Verma", "Bose", "Chakraborty", "Iyer",
)
ROADS = (
    "Lake Road", "Central Avenue", "Park Street", "Station Road",
    "Hospital Road", "Market Street", "College Road", "Circular Road",
)
LOCALITIES = (
    "Salt Lake", "New Town", "Ballygunge", "Garia", "Dum Dum",
    "Jadavpur", "Tollygunge", "Kasba", "Rajarhat", "Behala",
)
FACILITIES = (
    ("Wheelchair Accessible", "fa-solid fa-wheelchair"),
    ("Digital Payments", "fa-solid fa-credit-card"),
    ("Air Conditioned", "fa-solid fa-snowflake"),
    ("Parking Available", "fa-solid fa-square-parking"),
    ("Waiting Lounge", "fa-solid fa-couch"),
    ("Emergency Support", "fa-solid fa-kit-medical"),
    ("Online Reports", "fa-solid fa-file-waveform"),
    ("Home Service", "fa-solid fa-house-medical"),
)
GENERIC_SERVICES = (
    "Doctor Consultation", "Preventive Health Check-up", "Follow-up Care",
    "Online Appointment", "Patient Counselling", "Emergency Guidance",
)
SERVICE_MAP = {
    "Pharmacy": ("Prescription Medicines", "Generic Medicines", "Home Delivery", "Health Essentials"),
    "Hospital": ("Outpatient Consultation", "Emergency Care", "Day Care Procedures", "Health Check-up"),
    "Clinic": ("General Consultation", "Follow-up Care", "Vaccination", "Preventive Screening"),
    "Diagnostic Centre": ("Blood Tests", "Health Packages", "ECG", "Home Sample Collection"),
    "Pathology Laboratory": ("Blood Tests", "Urine Tests", "Thyroid Profile", "Home Sample Collection"),
    "Imaging Centre": ("X-Ray", "Ultrasound", "CT Scan", "MRI Scan"),
    "Dental Clinic": ("Dental Consultation", "Cleaning", "Root Canal", "Dental X-Ray"),
    "Eye Care Centre": ("Eye Examination", "Vision Testing", "Cataract Consultation", "Glaucoma Screening"),
    "Physiotherapy Centre": ("Pain Management", "Sports Rehabilitation", "Post-operative Rehab", "Home Physiotherapy"),
    "Mental Health Centre": ("Psychiatric Consultation", "Counselling", "Stress Management", "Family Therapy"),
    "Home Healthcare Service": ("Home Nursing", "Elder Care", "Physiotherapy at Home", "Medicine Support"),
    "Ambulance Service": ("Emergency Ambulance", "Patient Transfer", "ICU Ambulance", "Intercity Transfer"),
    "Blood Bank": ("Blood Availability", "Blood Donation", "Component Separation", "Emergency Support"),
    "Medical Equipment Supplier": ("Medical Equipment", "Equipment Rental", "Home Setup", "Maintenance Support"),
    "Vaccination Centre": ("Adult Vaccination", "Child Vaccination", "Travel Vaccination", "Vaccination Records"),
}
COLORS = (
    (16, 185, 129), (14, 165, 233), (99, 102, 241), (244, 63, 94),
    (245, 158, 11), (139, 92, 246), (20, 184, 166), (59, 130, 246),
)


def weekly_hours(index):
    if index % 7 == 0:
        return {}
    hours = {}
    for weekday in range(7):
        hours[str(weekday)] = [] if weekday == 6 and index % 3 else [
            {"opens_at": "08:30" if index % 2 else "09:00", "closes_at": "20:00"}
        ]
    return hours


def doctor_schedule(index):
    morning = index % 2 == 0
    return {
        "weekly": [{
            "weekdays": [0, 1, 2, 3, 4, 5],
            "slots": [{"start": "09:00" if morning else "16:00", "end": "13:00" if morning else "20:00"}],
            "note": "Appointments available Monday to Saturday",
        }],
        "monthly_weekday": [],
        "monthly_dates": [],
    }


def offset_coordinate(latitude, longitude, radius_km, rng):
    distance = radius_km * math.sqrt(rng.random())
    angle = rng.uniform(0, math.tau)
    lat = latitude + (distance * math.cos(angle)) / 111.195
    lng = longitude + (distance * math.sin(angle)) / (111.195 * math.cos(math.radians(latitude)))
    return Decimal(str(lat)).quantize(Decimal("0.000000001")), Decimal(str(lng)).quantize(Decimal("0.000000001"))


def demo_image(name, color):
    image = Image.new("RGB", (768, 480), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 330, 768, 480), fill=(15, 23, 42))
    draw.text((42, 365), name[:48], fill="white")
    draw.text((42, 405), "Trusted healthcare near you", fill=(167, 243, 208))
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return ContentFile(output.getvalue(), name="demo-profile.png")


class Command(BaseCommand):
    help = "Create or refresh a complete, presentable 20-business demo site."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20, help="Number of demo businesses (default: 20).")
        parser.add_argument("--center-lat", type=float, default=22.5726, help="Map centre latitude.")
        parser.add_argument("--center-lng", type=float, default=88.3639, help="Map centre longitude.")
        parser.add_argument("--radius-km", type=float, default=8, help="Distribution radius in kilometres.")
        parser.add_argument("--seed", type=int, default=2026, help="Seed for repeatable output.")
        parser.add_argument("--owner-phone", default="9000000000", help="Demo owner login phone number.")
        parser.add_argument("--owner-password", default="Demo@12345", help="Demo owner login password.")
        parser.add_argument("--skip-images", action="store_true", help="Skip generated demo thumbnail uploads.")

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        if count < 1:
            raise CommandError("--count must be at least 1.")
        if not -90 <= options["center_lat"] <= 90 or not -180 <= options["center_lng"] <= 180:
            raise CommandError("The centre latitude or longitude is invalid.")
        if options["radius_km"] < 0:
            raise CommandError("--radius-km cannot be negative.")

        call_command("seed_directory_categories", verbosity=0)
        rng = random.Random(options["seed"])
        business_categories = list(Category.objects.filter(type=Category.Type.BUSINESS_CATEGORY, is_active=True))
        specialties = list(Category.objects.filter(type=Category.Type.DOCTOR_SPECIALTY, is_active=True))
        if not business_categories or not specialties:
            raise CommandError("Business categories and doctor specialties are required.")

        state, _ = State.objects.get_or_create(name="West Bengal", defaults={"code": "WB"})
        city, _ = City.objects.get_or_create(name="Kolkata", state=state)
        localities = []
        for name in LOCALITIES:
            locality, _ = Locality.objects.get_or_create(name=name, city=city)
            localities.append(locality)

        User = get_user_model()
        owner, created = User.objects.get_or_create(
            phone=options["owner_phone"],
            defaults={"full_name": "MedNearby Demo Owner"},
        )
        owner.full_name = "MedNearby Demo Owner"
        owner.set_password(options["owner_password"])
        owner.save()

        facilities = []
        for name, icon in FACILITIES:
            facility = Facility.objects.filter(name=name).first()
            if facility is None:
                facility = Facility.objects.create(name=name, icon=icon)
            elif facility.icon != icon:
                facility.icon = icon
                facility.save(update_fields=["icon"])
            facilities.append(facility)

        businesses = []
        doctors_created = updates_created = leads_created = images_created = 0
        now = timezone.now()
        for index in range(count):
            number = index + 1
            primary = business_categories[index % len(business_categories)]
            business_name = f"{BRANDS[index % len(BRANDS)]} {primary.name}"
            email = f"showcase-business-{number:02d}@demo.mednearby.in"
            latitude, longitude = offset_coordinate(
                options["center_lat"], options["center_lng"], options["radius_km"], rng
            )
            business = Business.objects.filter(email=email).first()
            if business is None:
                business = Business(email=email)
            business.name = business_name
            business.owner = owner
            business.description = (
                f"{business_name} is a verified healthcare provider offering dependable, patient-friendly "
                f"services with experienced professionals, transparent support and modern facilities."
            )
            business.established_year = 2005 + index % 18
            business.address = f"{18 + index * 7}, {ROADS[index % len(ROADS)]}"
            business.landmark = f"Near {('Metro Station', 'Community Park', 'City Mall', 'Central Market')[index % 4]}"
            business.locality = localities[index % len(localities)]
            business.pincode = str(700001 + index)
            business.latitude = latitude
            business.longitude = longitude
            business.phone = f"+91910000{number:04d}"
            business.alternate_phone = f"+91920000{number:04d}"
            business.whatsapp = f"91910000{number:04d}"
            business.website = f"https://example.com/demo/{number}"
            business.tags = "Verified, Trusted, Same-day Service, Online Booking"
            business.services = list(SERVICE_MAP.get(primary.name, GENERIC_SERVICES))
            business.business_hours = weekly_hours(index)
            business.is_24_7 = index % 7 == 0
            business.is_appointment = True
            business.is_home_collection = primary.name in {"Diagnostic Centre", "Pathology Laboratory", "Home Healthcare Service"}
            business.is_home_delivery = primary.name in {"Pharmacy", "Medical Equipment Supplier"}
            business.is_emergency = primary.name in {"Hospital", "Ambulance Service", "Blood Bank"}
            business.is_testing = False
            business.is_active = True
            business.verification_status = Business.VerificationStatus.VERIFIED
            business.publication_status = Business.PublicationStatus.PUBLISHED
            business.save()
            business.categories.set([primary])
            business.facilities.set(rng.sample(facilities, 5))
            businesses.append(business)

            if not options["skip_images"] and not business.images.exists():
                BusinessImage.objects.create(
                    business=business,
                    image=demo_image(business.name, COLORS[index % len(COLORS)]),
                    is_thumbnail=True,
                )
                images_created += 1

            for doctor_number in range(2):
                doctor_index = index * 2 + doctor_number
                specialty = specialties[doctor_index % len(specialties)]
                doctor_name = f"Dr. {FIRST_NAMES[doctor_index % len(FIRST_NAMES)]} {LAST_NAMES[(doctor_index * 3) % len(LAST_NAMES)]}"
                doctor, was_created = Doctor.objects.update_or_create(
                    business=business,
                    name=doctor_name,
                    defaults={
                        "qualification": "MBBS, MD" if doctor_number == 0 else "MBBS, DNB",
                        "gender": Doctor.GenderChoices.FEMALE if doctor_index % 2 == 0 else Doctor.GenderChoices.MALE,
                        "fees": str(500 + (doctor_index % 8) * 100),
                        "bio": f"{doctor_name} provides evidence-based, compassionate care with a focus on clear communication and preventive health.",
                        "schedule": doctor_schedule(doctor_index),
                        "is_active": True,
                        "is_featured": doctor_index < 8,
                    },
                )
                doctor.specialties.set([specialty])
                doctors_created += int(was_created)

            update_templates = (
                (BusinessUpdate.Kind.ANNOUNCEMENT, "Extended consultation hours", "More appointment slots are now available.", "We have extended consultation hours for patient convenience. Please contact our team to confirm your preferred slot."),
                (BusinessUpdate.Kind.OFFER, "Complete health package", "Book a curated preventive health package this month.", "The package includes essential screening and a professional review. Contact us for inclusions, eligibility and appointment availability."),
            )
            for kind, title, summary, details in update_templates:
                _, was_created = BusinessUpdate.objects.update_or_create(
                    business=business,
                    title=title,
                    defaults={
                        "kind": kind,
                        "summary": summary,
                        "details": details,
                        "starts_at": now,
                        "ends_at": now + timedelta(days=60) if kind == BusinessUpdate.Kind.OFFER else None,
                        "is_published": True,
                    },
                )
                updates_created += int(was_created)

            for lead_number, status in enumerate((Lead.Status.NEW, Lead.Status.CONFIRMED), start=1):
                _, was_created = Lead.objects.update_or_create(
                    business=business,
                    patient_name=f"Demo Patient {number}-{lead_number}",
                    phone=f"98000{number:03d}{lead_number:02d}",
                    defaults={
                        "lead_type": Lead.LeadType.ENQUIRY,
                        "service": business.services[(lead_number - 1) % len(business.services)],
                        "message": "Please share availability and booking details.",
                        "status": status,
                        "is_archived": False,
                    },
                )
                leads_created += int(was_created)

            if primary.name == "Ambulance Service":
                Ambulance.objects.update_or_create(
                    business=business,
                    defaults={"phone": business.phone, "is_active": True, "is_24_7": True},
                )

        # Ensure every active business category is represented, even when count is smaller.
        for index, category in enumerate(business_categories):
            businesses[index % len(businesses)].categories.add(category)

        self.stdout.write(self.style.SUCCESS(
            f"Demo site ready: {len(businesses)} businesses, {count * 2} doctors, "
            f"{count * 2} updates and {count * 2} leads. "
            f"New records: {doctors_created} doctors, {updates_created} updates, "
            f"{leads_created} leads and {images_created} images."
        ))
        self.stdout.write(
            f"Demo owner login: {options['owner_phone']} / {options['owner_password']}"
        )
