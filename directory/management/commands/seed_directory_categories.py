from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from directory.models import Category


BUSINESS_CATEGORIES = (
    ("Pharmacy", "Pharmacies", "pharmacies", "fa-solid fa-prescription-bottle-medical", "medicine,chemist,medical store"),
    ("Hospital", "Hospitals", "hospitals", "fa-solid fa-hospital", "medical centre,nursing home"),
    ("Clinic", "Clinics", "clinics", "fa-solid fa-house-chimney-medical", "medical clinic,health clinic"),
    ("Diagnostic Centre", "Diagnostic Centres", "diagnostic-centres", "fa-solid fa-microscope", "diagnostics,pathology,lab"),
    ("Pathology Laboratory", "Pathology Laboratories", "pathology-laboratories", "fa-solid fa-flask-vial", "blood test,pathology lab"),
    ("Imaging Centre", "Imaging Centres", "imaging-centres", "fa-solid fa-x-ray", "x-ray,mri,ct scan,ultrasound"),
    ("Dental Clinic", "Dental Clinics", "dental-clinics", "fa-solid fa-tooth", "dentist,dental care"),
    ("Eye Care Centre", "Eye Care Centres", "eye-care-centres", "fa-solid fa-eye", "optical,ophthalmology,eye clinic"),
    ("Physiotherapy Centre", "Physiotherapy Centres", "physiotherapy-centres", "fa-solid fa-person-walking", "physio,rehabilitation"),
    ("Mental Health Centre", "Mental Health Centres", "mental-health-centres", "fa-solid fa-brain", "counselling,psychology,psychiatry"),
    ("Home Healthcare Service", "Home Healthcare Services", "home-healthcare-services", "fa-solid fa-house-medical-circle-check", "home nursing,home care"),
    ("Ambulance Service", "Ambulance Services", "ambulance-services", "fa-solid fa-truck-medical", "emergency transport"),
    ("Blood Bank", "Blood Banks", "blood-banks", "fa-solid fa-droplet", "blood donation,blood centre"),
    ("Medical Equipment Supplier", "Medical Equipment Suppliers", "medical-equipment-suppliers", "fa-solid fa-stethoscope", "medical devices,health equipment"),
    ("Vaccination Centre", "Vaccination Centres", "vaccination-centres", "fa-solid fa-syringe", "immunisation,vaccine"),
)

DOCTOR_SPECIALTIES = (
    ("General Medicine", "General Physicians", "general-physicians", "fa-solid fa-user-doctor", "physician,general doctor"),
    ("Cardiology", "Cardiologists", "cardiologists", "fa-solid fa-heart-pulse", "heart doctor,cardiac"),
    ("Dermatology", "Dermatologists", "dermatologists", "fa-solid fa-hand-dots", "skin doctor,hair specialist"),
    ("Pediatrics", "Pediatricians", "pediatricians", "fa-solid fa-baby", "child specialist,children doctor"),
    ("Gynecology", "Gynecologists", "gynecologists", "fa-solid fa-venus", "women's health,obstetrics"),
    ("Orthopedics", "Orthopedic Doctors", "orthopedic-doctors", "fa-solid fa-bone", "bone doctor,joint specialist"),
    ("Neurology", "Neurologists", "neurologists", "fa-solid fa-brain", "brain doctor,nerve specialist"),
    ("Psychiatry", "Psychiatrists", "psychiatrists", "fa-solid fa-head-side-virus", "mental health doctor"),
    ("Ophthalmology", "Ophthalmologists", "ophthalmologists", "fa-solid fa-eye", "eye doctor"),
    ("Otolaryngology", "ENT Specialists", "ent-specialists", "fa-solid fa-ear-listen", "ear nose throat,ent doctor"),
    ("Dentistry", "Dentists", "dentists", "fa-solid fa-tooth", "dental doctor"),
    ("Pulmonology", "Pulmonologists", "pulmonologists", "fa-solid fa-lungs", "lung doctor,chest specialist"),
    ("Gastroenterology", "Gastroenterologists", "gastroenterologists", "fa-solid fa-stomach", "digestive specialist,stomach doctor"),
    ("Nephrology", "Nephrologists", "nephrologists", "fa-solid fa-kidneys", "kidney doctor"),
    ("Urology", "Urologists", "urologists", "fa-solid fa-user-doctor", "urinary specialist"),
    ("Endocrinology", "Endocrinologists", "endocrinologists", "fa-solid fa-vials", "diabetes doctor,hormone specialist"),
    ("Oncology", "Oncologists", "oncologists", "fa-solid fa-ribbon", "cancer specialist"),
    ("Rheumatology", "Rheumatologists", "rheumatologists", "fa-solid fa-hand", "arthritis specialist"),
    ("General Surgery", "General Surgeons", "general-surgeons", "fa-solid fa-user-doctor", "surgeon,surgery"),
    ("Neurosurgery", "Neurosurgeons", "neurosurgeons", "fa-solid fa-brain", "brain surgeon,spine surgeon"),
    ("Plastic Surgery", "Plastic Surgeons", "plastic-surgeons", "fa-solid fa-user-doctor", "cosmetic surgeon,reconstructive surgery"),
    ("Anesthesiology", "Anesthesiologists", "anesthesiologists", "fa-solid fa-mask-face", "anaesthesia,pain management"),
    ("Radiology", "Radiologists", "radiologists", "fa-solid fa-x-ray", "imaging doctor"),
    ("Pathology", "Pathologists", "pathologists", "fa-solid fa-microscope", "laboratory doctor"),
    ("Physiotherapy", "Physiotherapists", "physiotherapists", "fa-solid fa-person-walking", "physical therapy,rehabilitation"),
)


class Command(BaseCommand):
    help = "Seed production business categories and doctor specialties."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the changes without committing them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0
        entries = (
            (Category.Type.BUSINESS_CATEGORY, BUSINESS_CATEGORIES),
            (Category.Type.DOCTOR_SPECIALTY, DOCTOR_SPECIALTIES),
        )

        for category_type, category_entries in entries:
            for display_order, entry in enumerate(category_entries, start=1):
                name, label, slug, icon, aliases = entry
                matches = list(
                    Category.objects.filter(type=category_type)
                    .filter(Q(name=name) | Q(slug=slug))
                    .distinct()[:2]
                )
                if len(matches) > 1:
                    raise CommandError(
                        f"Conflicting categories found for {name!r} and slug {slug!r}."
                    )

                defaults = {
                    "name": name,
                    "label": label,
                    "slug": slug,
                    "type": category_type,
                    "parent": None,
                    "aliases": aliases,
                    "icon": icon,
                    "display_order": display_order,
                    "is_featured": display_order <= 8,
                    "is_active": True,
                }
                if matches:
                    category = matches[0]
                    for field, value in defaults.items():
                        setattr(category, field, value)
                    category.save(update_fields=defaults.keys())
                    updated += 1
                else:
                    if Category.objects.filter(name=name).exists():
                        raise CommandError(
                            f"A category named {name!r} already exists with another type."
                        )
                    Category.objects.create(**defaults)
                    created += 1

        if options["dry_run"]:
            transaction.set_rollback(True)
            prefix = "Dry run: "
        else:
            prefix = ""

        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}created {created} and updated {updated} directory categories."
            )
        )
