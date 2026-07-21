import math
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import BytesIO, StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from PIL import Image

from .models import Ambulance, Business, BusinessImage, BusinessUpdate, Category, Doctor, Facility, Lead
from .services import (
    business_open_status,
    doctor_schedule_availability,
    serialize_business,
)


class BusinessImageTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.business = Business.objects.create(name="Image Test Clinic")

    @staticmethod
    def upload(width=1200, height=600, name="clinic.jpg", image_format="JPEG"):
        output = BytesIO()
        Image.new("RGB", (width, height), "white").save(output, image_format)
        return SimpleUploadedFile(
            name,
            output.getvalue(),
            content_type=f"image/{image_format.lower()}",
        )

    def test_converts_compresses_and_resizes_image_to_webp(self):
        business_image = BusinessImage.objects.create(
            business=self.business,
            image=self.upload(),
        )

        self.assertTrue(business_image.image.name.endswith(".webp"))
        with Image.open(business_image.image.path) as saved_image:
            self.assertEqual(saved_image.format, "WEBP")
            self.assertEqual(saved_image.size, (768, 384))

    def test_does_not_upscale_smaller_image(self):
        business_image = BusinessImage.objects.create(
            business=self.business,
            image=self.upload(width=400, height=700),
        )

        with Image.open(business_image.image.path) as saved_image:
            self.assertEqual(saved_image.size, (400, 700))

    def test_rejects_file_that_is_not_an_image(self):
        invalid_file = SimpleUploadedFile(
            "not-an-image.jpg",
            b"plain text",
            content_type="image/jpeg",
        )

        with self.assertRaises(ValidationError):
            BusinessImage.objects.create(
                business=self.business,
                image=invalid_file,
            )

    def test_selecting_thumbnail_updates_business_and_replaces_old_selection(self):
        first = BusinessImage.objects.create(
            business=self.business,
            image=self.upload(name="first.jpg"),
            is_thumbnail=True,
        )
        second = BusinessImage.objects.create(
            business=self.business,
            image=self.upload(name="second.jpg"),
            is_thumbnail=True,
        )

        first.refresh_from_db()
        self.business.refresh_from_db()
        self.assertFalse(first.is_thumbnail)
        self.assertTrue(second.is_thumbnail)
        self.assertEqual(self.business.thumbnail_url, second.image.name)


class BusinessOpenStatusTests(TestCase):
    hours = {
        "0": [
            {"opens_at": "09:00", "closes_at": "15:00"},
            {"opens_at": "18:00", "closes_at": "21:00"},
        ],
        "1": [{"opens_at": "09:00", "closes_at": "18:00"}],
        "2": [],
        "3": [],
        "4": [],
        "5": [],
        "6": [],
    }

    def test_open_slot_more_than_one_hour_before_close_returns_open(self):
        now = datetime(2026, 7, 13, 4, 30, tzinfo=dt_timezone.utc)  # 10:00 IST

        self.assertEqual(
            business_open_status(self.hours, now),
            (True, ""),
        )

    def test_24_7_business_is_always_open_without_saved_hours(self):
        self.assertEqual(
            business_open_status({}, is_24_7=True),
            (True, "Open 24 Hours"),
        )

    def test_open_slot_less_than_one_hour_before_close_returns_closing_status(self):
        now = datetime(2026, 7, 13, 8, 31, tzinfo=dt_timezone.utc)  # 14:01 IST

        self.assertEqual(
            business_open_status(self.hours, now),
            (True, "Closes at 3PM"),
        )

    def test_exactly_one_hour_before_close_returns_open(self):
        now = datetime(2026, 7, 13, 8, 30, tzinfo=dt_timezone.utc)  # 14:00 IST

        self.assertEqual(business_open_status(self.hours, now), (True, ""))

    def test_split_shift_returns_closed_status(self):
        now = datetime(2026, 7, 13, 11, 0, tzinfo=dt_timezone.utc)  # 16:30 IST

        self.assertEqual(
            business_open_status(self.hours, now),
            (False, "Open 6PM"),
        )

    def test_closed_day_returns_closed_status(self):
        now = datetime(2026, 7, 15, 4, 30, tzinfo=dt_timezone.utc)  # Wednesday 10:00 IST

        self.assertEqual(
            business_open_status(self.hours, now),
            (False, "Open Monday 9AM"),
        )

    def test_overnight_slot_is_open_on_following_day(self):
        hours = {str(day): [] for day in range(7)}
        hours["0"] = [{"opens_at": "22:00", "closes_at": "02:00"}]
        now = datetime(2026, 7, 13, 19, 30, tzinfo=dt_timezone.utc)  # Tuesday 01:00 IST

        self.assertEqual(
            business_open_status(hours, now),
            (True, ""),
        )

    def test_closed_status_returns_tomorrows_opening_time(self):
        now = datetime(2026, 7, 13, 16, 0, tzinfo=dt_timezone.utc)  # Monday 21:30 IST

        self.assertEqual(
            business_open_status(self.hours, now),
            (False, "Open Tomorrow 9AM"),
        )


class DoctorScheduleAvailabilityTests(TestCase):
    def test_weekly_schedule_returns_available_today(self):
        schedule = {
            "weekly": [{"weekdays": [0], "slots": [{"start": "09:00", "end": "13:00"}]}]
        }
        now = datetime(2026, 7, 13, 4, 30, tzinfo=dt_timezone.utc)  # Monday 10:00 IST

        result = doctor_schedule_availability(schedule, now)

        self.assertTrue(result["is_today"])
        self.assertEqual(result["next_time"], "9AM - 1PM")

    def test_ended_slot_today_returns_next_schedule(self):
        schedule = {
            "weekly": [{"weekdays": [0], "slots": [{"start": "09:00", "end": "12:00"}]}]
        }
        now = datetime(2026, 7, 13, 8, 30, tzinfo=dt_timezone.utc)  # Monday 2:00 PM IST

        result = doctor_schedule_availability(schedule, now)

        self.assertFalse(result["is_today"])
        self.assertEqual(result["next_date"], "Mon, 20 Jul")
        self.assertEqual(result["next_time"], "9AM - 12PM")

    def test_monthly_weekday_supports_last_occurrence(self):
        schedule = {
            "monthly_weekday": [
                {"weekdays": [0], "week_numbers": [-1], "slots": [{"start": "10:00", "end": "14:00"}]}
            ]
        }
        now = datetime(2026, 7, 20, 4, 30, tzinfo=dt_timezone.utc)

        result = doctor_schedule_availability(schedule, now)

        self.assertFalse(result["is_today"])
        self.assertEqual(result["next_date"], "Mon, 27 Jul")

    def test_monthly_date_returns_selected_date(self):
        schedule = {
            "monthly_dates": [
                {"dates": [15], "slots": [{"start": "11:00", "end": "15:00"}]}
            ]
        }
        now = datetime(2026, 7, 13, 4, 30, tzinfo=dt_timezone.utc)

        result = doctor_schedule_availability(schedule, now)

        self.assertEqual(result["next_date"], "Wed, 15 Jul")
        self.assertIn("display_rows", result)
        self.assertEqual(result["display_rows"][0]["label"], "15th of every month")


class AddDummyDoctorsCommandTests(TestCase):
    def setUp(self):
        self.specialty = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        Category.objects.create(
            name="Pharmacy",
            type=Category.Type.BUSINESS_CATEGORY,
        )
        self.business = Business.objects.create(name="City Clinic")

    def test_creates_requested_doctors_with_doctor_specialties(self):
        output = StringIO()

        call_command("add_dummy_doctors", 5, seed=7, stdout=output)

        self.assertEqual(Doctor.objects.count(), 5)
        self.assertTrue(
            all(
                doctor.business == self.business
                and list(doctor.specialties.all()) == [self.specialty]
                for doctor in Doctor.objects.prefetch_related("specialties")
            )
        )
        self.assertIn("Created 5 dummy doctors", output.getvalue())

    def test_requires_an_active_doctor_specialty(self):
        self.specialty.is_active = False
        self.specialty.save(update_fields=["is_active"])

        with self.assertRaisesMessage(
            CommandError,
            "No active doctor specialties exist",
        ):
            call_command("add_dummy_doctors", 1)


class AddDummyUpdatesCommandTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Published Clinic",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        Business.objects.create(
            name="Draft Clinic",
            publication_status=Business.PublicationStatus.DRAFT,
        )

    def test_adds_requested_updates_to_published_businesses_idempotently(self):
        output = StringIO()

        call_command("add_dummy_updates", 4, seed=7, stdout=output)
        call_command("add_dummy_updates", 4, seed=7, stdout=output)

        updates = BusinessUpdate.objects.filter(business=self.business)
        self.assertEqual(updates.count(), 4)
        self.assertTrue(updates.filter(kind=BusinessUpdate.Kind.OFFER).exists())
        self.assertEqual(BusinessUpdate.objects.filter(business__name="Draft Clinic").count(), 0)
        self.assertIn("already existed", output.getvalue())

    def test_can_target_a_business_by_slug(self):
        other = Business.objects.create(
            name="Other Published Clinic",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )

        call_command("add_dummy_updates", 2, business_slug=other.slug, verbosity=0)

        self.assertEqual(BusinessUpdate.objects.filter(business=other).count(), 2)
        self.assertFalse(BusinessUpdate.objects.filter(business=self.business).exists())

    def test_rejects_non_positive_count(self):
        with self.assertRaises(CommandError):
            call_command("add_dummy_updates", 0)


class AddDummyAmbulancesCommandTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Active Clinic")
        Business.objects.create(
            name="Testing Clinic",
            is_testing=True,
        )

    def test_creates_requested_ambulances_for_eligible_businesses(self):
        output = StringIO()

        call_command("add_dummy_ambulances", 5, seed=42, stdout=output)

        self.assertEqual(Ambulance.objects.count(), 5)
        self.assertEqual(
            set(Ambulance.objects.values_list("business_id", flat=True)),
            {self.business.id},
        )
        self.assertEqual(
            Ambulance.objects.values("phone").distinct().count(),
            5,
        )
        self.assertEqual(Ambulance.objects.filter(is_active=True).count(), 5)
        self.assertIn("Created 5 dummy ambulances", output.getvalue())

    def test_requires_an_eligible_business(self):
        self.business.is_active = False
        self.business.save(update_fields=["is_active"])

        with self.assertRaisesMessage(
            CommandError,
            "No active non-testing businesses exist",
        ):
            call_command("add_dummy_ambulances", 1)

    def test_rejects_invalid_count(self):
        with self.assertRaisesMessage(CommandError, "count must be at least 1"):
            call_command("add_dummy_ambulances", 0)


class AddRandomDoctorSchedulesCommandTests(TestCase):
    def setUp(self):
        self.doctors = [Doctor.objects.create(name=f"Doctor {number}") for number in range(3)]

    def test_adds_valid_schedule_to_every_doctor(self):
        call_command("add_random_doctor_schedules", seed=42)

        for doctor in self.doctors:
            doctor.refresh_from_db()
            self.assertEqual(
                set(doctor.schedule),
                {"weekly", "monthly_weekday", "monthly_dates"},
            )
            self.assertTrue(doctor.schedule["weekly"])
            for entry in doctor.schedule["weekly"]:
                self.assertTrue(all(0 <= day <= 6 for day in entry["weekdays"]))
                self.assertTrue(entry["slots"])
                self.assertTrue(entry["note"])
            for entry in doctor.schedule["monthly_weekday"]:
                self.assertTrue(set(entry["week_numbers"]) <= {1, 2, 3, 4, -1})
            for entry in doctor.schedule["monthly_dates"]:
                self.assertTrue(all(1 <= date <= 28 for date in entry["dates"]))

    def test_preserves_existing_schedule_without_overwrite(self):
        existing = {"weekly": [{"weekdays": [0], "slots": [], "note": "Existing"}]}
        self.doctors[0].schedule = existing
        self.doctors[0].save(update_fields=["schedule"])

        call_command("add_random_doctor_schedules", seed=42)

        self.doctors[0].refresh_from_db()
        self.assertEqual(self.doctors[0].schedule, existing)

    def test_overwrite_replaces_existing_schedule(self):
        self.doctors[0].schedule = {"existing": True}
        self.doctors[0].save(update_fields=["schedule"])

        call_command("add_random_doctor_schedules", seed=42, overwrite=True)

        self.doctors[0].refresh_from_db()
        self.assertNotIn("existing", self.doctors[0].schedule)


class AddRandomDoctorFeesCommandTests(TestCase):
    def setUp(self):
        self.doctors = [Doctor.objects.create(name=f"Fee Doctor {number}") for number in range(3)]

    def test_adds_fees_within_configured_range(self):
        call_command("add_random_doctor_fees", seed=42, min_fee=500, max_fee=900, step=100)

        for doctor in self.doctors:
            doctor.refresh_from_db()
            self.assertIn(doctor.fees, {"500", "600", "700", "800", "900"})

    def test_preserves_existing_fee_without_overwrite(self):
        self.doctors[0].fees = "1500"
        self.doctors[0].save(update_fields=["fees"])

        call_command("add_random_doctor_fees", seed=42)

        self.doctors[0].refresh_from_db()
        self.assertEqual(self.doctors[0].fees, "1500")

    def test_overwrite_replaces_existing_fee(self):
        self.doctors[0].fees = "1500"
        self.doctors[0].save(update_fields=["fees"])

        call_command(
            "add_random_doctor_fees",
            seed=42,
            min_fee=500,
            max_fee=500,
            overwrite=True,
        )

        self.doctors[0].refresh_from_db()
        self.assertEqual(self.doctors[0].fees, "500")


class CategorySearchViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Category.objects.create(
            name="Cardiology",
            label="Cardiologists",
            type=Category.Type.DOCTOR_SPECIALTY,
            aliases="heart, cardiac",
            synonyms="Heart doctor, Heart specialist",
        )
        cls.business = Category.objects.create(
            name="Pharmacy",
            type=Category.Type.BUSINESS_CATEGORY,
            aliases="medicine, chemist",
        )
        Category.objects.create(name="Inactive Clinic", is_active=False)

    def search(self, query):
        return self.client.get(reverse("directory:category-search"), {"q": query})

    def test_search_matches_alias_and_returns_specialty_destination(self):
        response = self.search("heart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"],
            [
                {
                    "name": "Cardiology",
                    "label": "Cardiologists",
                    "slug": "cardiology",
                    "type": "specialty",
                    "type_label": "Doctor Specialty",
                    "icon": "",
                    "synonyms": "Heart doctor, Heart specialist",
                    "url": "/doctors/cardiology",
                }
            ],
        )

    def test_business_category_uses_business_destination(self):
        result = self.search("Pharmacy").json()["results"][0]

        self.assertEqual(result["type"], "category")
        self.assertEqual(result["url"], "/category/pharmacy")

    def test_search_matches_and_returns_specialty_synonyms(self):
        result = self.search("Heart specialist").json()["results"][0]

        self.assertEqual(result["name"], "Cardiology")
        self.assertEqual(result["synonyms"], "Heart doctor, Heart specialist")

    def test_inactive_categories_are_excluded(self):
        self.assertEqual(self.search("Inactive").json()["results"], [])

    def test_empty_query_returns_no_results(self):
        self.assertEqual(self.search("").json()["results"], [])

    def test_post_is_not_allowed(self):
        response = self.client.post(reverse("directory:category-search"))

        self.assertEqual(response.status_code, 405)


class DoctorSpecialtyListViewTests(TestCase):
    def test_lists_only_active_doctor_specialties(self):
        cardiology = Category.objects.create(
            name="Cardiology",
            label="Cardiologists",
            type=Category.Type.DOCTOR_SPECIALTY,
            synonyms="Heart doctor, Heart specialist",
        )
        Category.objects.create(name="Pharmacy")
        Category.objects.create(
            name="Inactive Specialty",
            type=Category.Type.DOCTOR_SPECIALTY,
            is_active=False,
        )

        response = self.client.get(reverse("doctors:specialties"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["specialties"], [cardiology])
        self.assertContains(response, "Cardiologists")
        self.assertContains(response, "Heart doctor, Heart specialist")
        self.assertContains(
            response,
            reverse("doctors:list", kwargs={"slug": cardiology.slug}),
        )
        self.assertNotContains(response, "Pharmacy")
        self.assertNotContains(response, "Inactive Specialty")

    def test_doctors_url_has_no_trailing_slash(self):
        response = self.client.get("/doctors")

        self.assertEqual(response.status_code, 200)

    def test_navigation_and_location_controls_are_connected(self):
        response = self.client.get(reverse("doctors:specialties"))

        self.assertContains(response, 'id="doctor-specialties-back"')
        self.assertContains(response, reverse("core:home"))
        self.assertContains(response, 'data-bottom-sheet-target="#location-sheet"')
        self.assertContains(response, 'id="selected-location-name"')

    def test_uses_configured_icons_fallback_and_unique_colors(self):
        Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
            icon="fa-solid fa-heart-pulse",
            is_featured=True,
        )
        Category.objects.create(
            name="Neurology",
            type=Category.Type.DOCTOR_SPECIALTY,
            is_featured=True,
        )

        response = self.client.get(reverse("doctors:specialties"))
        specialties = response.context["specialties"]

        self.assertEqual(
            len({specialty.icon_style for specialty in specialties}),
            len(specialties),
        )
        self.assertContains(response, "fa-solid fa-heart-pulse")
        self.assertContains(response, "fa-solid fa-user-doctor")


class BusinessGeohashTests(TestCase):
    def test_save_generates_precision_twelve_geohash(self):
        business = Business.objects.create(
            name="City Pharmacy",
            latitude="22.586700000",
            longitude="88.417100000",
        )

        self.assertEqual(business.geohash, "tunb7zz35f01")
        self.assertEqual(len(business.geohash), 12)

    def test_save_clears_geohash_when_coordinate_is_removed(self):
        business = Business.objects.create(
            name="City Pharmacy",
            latitude="22.586700000",
            longitude="88.417100000",
        )
        business.latitude = None
        business.save()

        self.assertIsNone(business.geohash)

    def test_partial_coordinate_save_also_persists_geohash(self):
        business = Business.objects.create(
            name="City Pharmacy",
            latitude="22.586700000",
            longitude="88.417100000",
        )
        original_geohash = business.geohash
        business.latitude = "22.600000000"
        business.save(update_fields={"latitude"})
        business.refresh_from_db()

        self.assertNotEqual(business.geohash, original_geohash)
        self.assertEqual(business.geohash, "tunbefpqec25")


class BusinessSlugTests(TestCase):
    def test_slug_combines_business_name_and_landmark(self):
        business = Business.objects.create(
            name="City Health Clinic",
            landmark="Near Central Park",
        )

        self.assertEqual(
            business.slug,
            "city-health-clinic-near-central-park",
        )

    def test_slug_updates_when_landmark_changes(self):
        business = Business.objects.create(
            name="City Health Clinic",
            landmark="Central Park",
        )

        business.landmark = "Railway Station"
        business.save(update_fields=["landmark"])

        self.assertEqual(business.slug, "city-health-clinic-railway-station")

    def test_duplicate_business_and_landmark_gets_unique_slug(self):
        Business.objects.create(name="City Clinic", landmark="Main Road")
        duplicate = Business.objects.create(name="City Clinic", landmark="Main Road")

        self.assertEqual(duplicate.slug, "city-clinic-main-road-2")


class LeadWorkflowTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            phone="9888888888", full_name="Lead Owner", password="safe-password"
        )
        self.business = Business.objects.create(
            name="Lead Clinic", owner=self.owner, services=["Blood Test", "Consultation"]
        )
        self.doctor = Doctor.objects.create(name="Dr Lead", business=self.business)

    def test_appointment_submission_creates_new_lead_for_selected_doctor(self):
        response = self.client.post(
            reverse("doctors:book-appointment", args=[self.doctor.slug]),
            {"patient_name": "Patient One", "phone": "9876543210", "message": "Morning"},
        )

        self.assertEqual(response.status_code, 200)
        lead = Lead.objects.get()
        self.assertEqual(lead.doctor, self.doctor)
        self.assertEqual(lead.business, self.business)
        self.assertEqual(lead.lead_type, Lead.LeadType.APPOINTMENT)
        self.assertEqual(lead.status, Lead.Status.NEW)

    def test_enquiry_submission_accepts_only_business_service(self):
        response = self.client.post(
            reverse("businesses:send-enquiry", args=[self.business.slug]),
            {"patient_name": "Patient Two", "phone": "9876543211", "service": "Blood Test"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Lead.objects.get().service, "Blood Test")

        invalid = self.client.post(
            reverse("businesses:send-enquiry", args=[self.business.slug]),
            {"patient_name": "Patient Three", "phone": "9876543212", "service": "Unknown"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_enquiry_submission_is_unavailable_when_business_disables_it(self):
        self.business.is_appointment = False
        self.business.save(update_fields=["is_appointment"])

        response = self.client.post(
            reverse("businesses:send-enquiry", args=[self.business.slug]),
            {"patient_name": "Patient Two", "phone": "9876543211"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Lead.objects.exists())

    def test_lead_submission_rejects_non_numeric_or_non_ten_digit_phone(self):
        url = reverse("doctors:book-appointment", args=[self.doctor.slug])
        for phone in ("98765abcde", "98765432101", "987654321"):
            response = self.client.post(
                url, {"patient_name": "Invalid Phone", "phone": phone}
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Lead.objects.exists())

    def test_owner_lead_page_is_private_and_supports_status_and_delete(self):
        lead = Lead.objects.create(
            business=self.business, patient_name="Patient", phone="9876543210"
        )
        anonymous = self.client.get(reverse("businesses:leads", args=[self.business.slug]))
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.owner)
        page = self.client.get(reverse("businesses:leads", args=[self.business.slug]))
        self.assertContains(page, "Patient")
        self.assertNotContains(page, 'aria-label="Primary navigation"')

        action_url = reverse("businesses:lead-action", args=[self.business.slug, lead.id])
        self.assertEqual(self.client.post(action_url, {"status": Lead.Status.CONTACTED}).status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.CONTACTED)
        self.assertEqual(self.client.post(action_url, {"action": "delete"}).status_code, 200)
        self.assertFalse(Lead.objects.filter(pk=lead.pk).exists())

    def test_owner_can_toggle_a_lead_between_new_and_viewed(self):
        lead = Lead.objects.create(
            business=self.business,
            patient_name="Patient",
            phone="9876543210",
            status=Lead.Status.NEW,
        )
        self.client.force_login(self.owner)
        action_url = reverse("businesses:lead-action", args=[self.business.slug, lead.id])

        viewed = self.client.post(action_url, {"action": "toggle-viewed"})
        lead.refresh_from_db()
        self.assertEqual(viewed.json()["status"], Lead.Status.CONTACTED)
        self.assertEqual(lead.status, Lead.Status.CONTACTED)

        new = self.client.post(action_url, {"action": "toggle-viewed"})
        lead.refresh_from_db()
        self.assertEqual(new.json()["status"], Lead.Status.NEW)
        self.assertEqual(lead.status, Lead.Status.NEW)

    def test_lead_page_defaults_to_enquiries_and_counts_only_new_leads(self):
        Lead.objects.create(
            business=self.business,
            patient_name="New Enquiry",
            phone="9876543210",
            lead_type=Lead.LeadType.ENQUIRY,
            status=Lead.Status.NEW,
        )
        Lead.objects.create(
            business=self.business,
            patient_name="Contacted Enquiry",
            phone="9876543211",
            lead_type=Lead.LeadType.ENQUIRY,
            status=Lead.Status.CONTACTED,
        )
        Lead.objects.create(
            business=self.business,
            doctor=self.doctor,
            patient_name="New Appointment",
            phone="9876543212",
            lead_type=Lead.LeadType.APPOINTMENT,
            status=Lead.Status.NEW,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("businesses:leads", args=[self.business.slug]))

        self.assertEqual(response.context["new_enquiry_count"], 1)
        self.assertEqual(response.context["new_appointment_count"], 1)
        self.assertContains(response, 'data-lead-tab="enquiry"')
        self.assertContains(response, 'data-lead-panel="appointment" class="mt-3 hidden')

    def test_lead_page_defaults_to_last_seven_days_and_kolkata_time(self):
        recent = Lead.objects.create(
            business=self.business,
            patient_name="Recent Patient",
            phone="9876543210",
        )
        old = Lead.objects.create(
            business=self.business,
            patient_name="Old Patient",
            phone="9876543211",
        )
        Lead.objects.filter(pk=recent.pk).update(created_at=timezone.now())
        Lead.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("businesses:leads", args=[self.business.slug]))
        self.assertContains(response, "Recent Patient")
        self.assertNotContains(response, "Old Patient")
        self.assertContains(response, "Call Back")
        self.assertContains(response, "Viewed")
        self.assertNotContains(response, "<select")
        self.assertNotContains(response, ">9876543210</a>")

    def test_business_without_doctors_shows_single_lead_list_without_tabs(self):
        business = Business.objects.create(name="No Doctor Pharmacy", owner=self.owner)
        Lead.objects.create(
            business=business,
            patient_name="Enquiry Patient",
            phone="9876543210",
            lead_type=Lead.LeadType.ENQUIRY,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("businesses:leads", args=[business.slug]))

        self.assertContains(response, "Enquiry Patient")
        self.assertNotContains(response, 'role="tablist"')
        self.assertNotContains(response, "Appointments (")


class BusinessPhoneTests(TestCase):
    def test_missing_phone_uses_owner_phone_with_india_country_code(self):
        owner = get_user_model().objects.create_user(
            phone="9876543210",
            full_name="Clinic Owner",
        )

        business = Business.objects.create(name="City Clinic", owner=owner)

        self.assertEqual(business.phone, "+919876543210")

    def test_owner_phone_with_country_code_is_not_prefixed_twice(self):
        owner = get_user_model().objects.create_user(
            phone="+919876543210",
            full_name="Clinic Owner",
        )

        business = Business.objects.create(name="City Clinic", owner=owner)

        self.assertEqual(business.phone, "+919876543210")

    def test_provided_business_phone_is_preserved(self):
        owner = get_user_model().objects.create_user(
            phone="9876543210",
            full_name="Clinic Owner",
        )

        business = Business.objects.create(
            name="City Clinic",
            owner=owner,
            phone="9123456780",
        )

        self.assertEqual(business.phone, "9123456780")


class AddDummyBusinessesCommandTests(TestCase):
    def test_command_creates_geocoded_businesses_inside_radius(self):
        output = StringIO()
        call_command(
            "add_dummy_businesses",
            8,
            22.5726,
            88.3639,
            5,
            seed=42,
            stdout=output,
        )

        businesses = Business.objects.all()
        self.assertEqual(businesses.count(), 8)
        self.assertIn("Created 8 dummy businesses", output.getvalue())
        for business in businesses:
            self.assertEqual(len(business.geohash), 12)
            self.assertEqual(
                business.publication_status,
                Business.PublicationStatus.PUBLISHED,
            )
            self.assertLessEqual(
                self.distance_km(
                    22.5726,
                    88.3639,
                    float(business.latitude),
                    float(business.longitude),
                ),
                5.001,
            )

    def test_command_rejects_invalid_arguments(self):
        with self.assertRaisesMessage(CommandError, "count must be at least 1"):
            call_command("add_dummy_businesses", 0, 22.5, 88.3, 5)

    @staticmethod
    def distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
        latitude_1, longitude_1, latitude_2, longitude_2 = map(
            math.radians,
            (latitude_1, longitude_1, latitude_2, longitude_2),
        )
        latitude_delta = latitude_2 - latitude_1
        longitude_delta = longitude_2 - longitude_1
        haversine = (
            math.sin(latitude_delta / 2) ** 2
            + math.cos(latitude_1)
            * math.cos(latitude_2)
            * math.sin(longitude_delta / 2) ** 2
        )
        return 6371.0088 * 2 * math.asin(math.sqrt(haversine))


class AddRandomBusinessHoursCommandTests(TestCase):
    def test_adds_valid_seven_day_json_to_every_business(self):
        businesses = [
            Business.objects.create(name=f"Clinic {number}")
            for number in range(3)
        ]

        call_command("add_random_business_hours", seed=42)

        for business in businesses:
            business.refresh_from_db()
            self.assertEqual(set(business.business_hours), set("0123456"))
            for slots in business.business_hours.values():
                self.assertIsInstance(slots, list)
                for slot in slots:
                    self.assertEqual(set(slot), {"opens_at", "closes_at"})
                    self.assertRegex(slot["opens_at"], r"^\d{2}:\d{2}$")
                    self.assertRegex(slot["closes_at"], r"^\d{2}:\d{2}$")

    def test_preserves_existing_hours_without_overwrite(self):
        existing = {str(day): [] for day in range(7)}
        business = Business.objects.create(
            name="Existing Clinic",
            business_hours=existing,
        )

        call_command("add_random_business_hours", seed=42)

        business.refresh_from_db()
        self.assertEqual(business.business_hours, existing)

    def test_overwrite_replaces_existing_hours(self):
        existing = {str(day): [] for day in range(7)}
        business = Business.objects.create(
            name="Existing Clinic",
            business_hours=existing,
        )

        call_command("add_random_business_hours", seed=42, overwrite=True)

        business.refresh_from_db()
        self.assertNotEqual(business.business_hours, existing)


class PrepareDemoSiteCommandTests(TestCase):
    def test_creates_complete_repeatable_showcase_dataset(self):
        output = StringIO()

        call_command("prepare_demo_site", skip_images=True, stdout=output)

        businesses = Business.objects.filter(email__endswith="@demo.mednearby.in")
        self.assertEqual(businesses.count(), 20)
        self.assertEqual(
            businesses.values("categories").distinct().count(),
            Category.objects.filter(type=Category.Type.BUSINESS_CATEGORY).count(),
        )
        for business in businesses:
            self.assertTrue(business.description)
            self.assertTrue(business.full_address)
            self.assertTrue(business.phone)
            self.assertTrue(business.whatsapp)
            self.assertTrue(business.services)
            self.assertTrue(business.tags)
            self.assertEqual(business.facilities.count(), 5)
            self.assertEqual(Doctor.objects.filter(business=business).count(), 2)
            self.assertEqual(business.updates.count(), 2)
            self.assertEqual(business.leads.count(), 2)

        self.assertEqual(
            Doctor.objects.values("specialties").distinct().count(),
            Category.objects.filter(type=Category.Type.DOCTOR_SPECIALTY).count(),
        )
        self.assertIn("Demo site ready: 20 businesses", output.getvalue())

        call_command("prepare_demo_site", skip_images=True, stdout=StringIO())
        self.assertEqual(
            Business.objects.filter(email__endswith="@demo.mednearby.in").count(),
            20,
        )
        self.assertEqual(Doctor.objects.count(), 40)
        self.assertEqual(BusinessUpdate.objects.count(), 40)
        self.assertEqual(Lead.objects.count(), 40)

    def test_rejects_zero_businesses(self):
        with self.assertRaisesMessage(CommandError, "--count must be at least 1"):
            call_command("prepare_demo_site", count=0, skip_images=True)


class SeedDirectoryCategoriesCommandTests(TestCase):
    def test_creates_production_categories_with_plural_labels_and_slugs(self):
        output = StringIO()

        call_command("seed_directory_categories", stdout=output)

        self.assertEqual(
            Category.objects.filter(type=Category.Type.BUSINESS_CATEGORY).count(),
            15,
        )
        self.assertEqual(
            Category.objects.filter(type=Category.Type.DOCTOR_SPECIALTY).count(),
            25,
        )
        pharmacy = Category.objects.get(name="Pharmacy")
        cardiology = Category.objects.get(name="Cardiology")
        self.assertEqual(pharmacy.label, "Pharmacies")
        self.assertEqual(pharmacy.slug, "pharmacies")
        self.assertEqual(cardiology.label, "Cardiologists")
        self.assertEqual(cardiology.slug, "cardiologists")
        self.assertIn("created 40", output.getvalue())

    def test_is_idempotent(self):
        call_command("seed_directory_categories", verbosity=0)
        call_command("seed_directory_categories", verbosity=0)

        self.assertEqual(Category.objects.count(), 40)

    def test_dry_run_does_not_save_categories(self):
        call_command("seed_directory_categories", dry_run=True, verbosity=0)

        self.assertEqual(Category.objects.count(), 0)


class AssignRandomBusinessCategoriesCommandTests(TestCase):
    def setUp(self):
        self.categories = [
            Category.objects.create(name="Pharmacy"),
            Category.objects.create(name="Clinic"),
        ]
        self.businesses = [
            Business.objects.create(name=f"Business {number}")
            for number in range(3)
        ]

    def test_assigns_a_category_to_every_uncategorized_business(self):
        call_command("assign_random_business_categories", seed=42, verbosity=0)

        for business in self.businesses:
            self.assertEqual(business.categories.count(), 1)

    def test_preserves_existing_categories_without_overwrite(self):
        self.businesses[0].categories.set([self.categories[0]])

        call_command("assign_random_business_categories", seed=42, verbosity=0)

        self.assertEqual(
            list(self.businesses[0].categories.all()),
            [self.categories[0]],
        )

    def test_overwrite_replaces_existing_assignments_with_one_category(self):
        self.businesses[0].categories.set(self.categories)

        call_command(
            "assign_random_business_categories",
            seed=42,
            overwrite=True,
            verbosity=0,
        )

        self.assertEqual(self.businesses[0].categories.count(), 1)


class BusinessListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Pharmacies", label="Pharmacies")
        for number in range(12):
            business = Business.objects.create(
                name=f"Nearby Pharmacy {number}",
                latitude=str(22.5726 + number * 0.0001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
                is_active=True,
            )
            business.categories.add(cls.category)

        far_business = Business.objects.create(
            name="Far Pharmacy",
            latitude="28.613900000",
            longitude="77.209000000",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        far_business.categories.add(cls.category)
        draft_business = Business.objects.create(
            name="Draft Pharmacy",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.DRAFT,
        )
        draft_business.categories.add(cls.category)

    def setUp(self):
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

    def test_initial_page_returns_first_ten_nearest_businesses(self):
        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["businesses"]), 10)
        self.assertEqual(response.context["total_count"], 12)
        self.assertContains(response, "(12 results)")
        self.assertTrue(response.context["has_more"])
        self.assertEqual(
            response.context["businesses"][0]["name"],
            "Nearby Pharmacy 0",
        )
        self.assertNotContains(response, "Far Pharmacy")
        self.assertNotContains(response, "Draft Pharmacy")

    def test_open_now_filter_shows_zero_count_and_empty_state(self):
        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug})
        )

        self.assertEqual(response.context["open_now_count"], 0)
        self.assertContains(response, "Open Now (0)")
        self.assertContains(response, "No businesses are open now.")

    def test_24_7_business_counts_as_open_now_and_returns_24_hour_status(self):
        Business.objects.filter(name="Nearby Pharmacy 0").update(is_24_7=True)

        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug})
        )

        business = response.context["businesses"][0]
        self.assertEqual(response.context["open_now_count"], 1)
        self.assertTrue(business["is_open"])
        self.assertTrue(business["is_24_7"])
        self.assertEqual(business["open_status"], "Open 24 Hours")

    def test_ajax_second_page_returns_remaining_businesses(self):
        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug}),
            {"page": 2},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["results"]), 2)
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["next_page"], 3)
        self.assertEqual(payload["total_count"], 12)
        self.assertIn("is_open", payload["results"][0])
        self.assertIn("open_status", payload["results"][0])

    def test_page_without_coordinate_cookies_requests_location(self):
        self.client.cookies.clear()
        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["location_required"])
        self.assertContains(response, "Select your location")

    def test_non_business_category_is_not_available(self):
        specialty = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )

        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": specialty.slug})
        )

        self.assertEqual(response.status_code, 404)

    def test_testing_business_is_excluded_from_results(self):
        testing_business = Business.objects.create(
            name="Testing Pharmacy",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.PUBLISHED,
            is_active=True,
            is_testing=True,
        )
        testing_business.categories.add(self.category)
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

        response = self.client.get(
            reverse("businesses:list", kwargs={"slug": self.category.slug})
        )

        self.assertEqual(response.context["total_count"], 12)
        self.assertNotContains(response, "Testing Pharmacy")


class BusinessDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Pharmacy")
        cls.business = Business.objects.create(
            name="City Pharmacy",
            description="Trusted neighborhood pharmacy",
            established_year=2016,
            address="12 Main Road",
            landmark="Near City Park",
            phone="9876543210",
            alternate_phone="9876543211",
            whatsapp="919876543210",
            email="hello@citypharmacy.example",
            website="https://citypharmacy.example",
            latitude="22.572600000",
            longitude="88.363900000",
            business_hours={"0": [{"opens_at": "09:00", "closes_at": "18:00"}]},
            publication_status=Business.PublicationStatus.PUBLISHED,
            is_active=True,
        )
        cls.business.categories.add(cls.category)

    def test_displays_published_active_business(self):
        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["business"], self.business)
        self.assertContains(response, "City Pharmacy")
        self.assertContains(response, "Trusted neighborhood pharmacy")
        self.assertContains(response, "City Pharmacy")
        self.assertContains(response, "Year")
        self.assertNotContains(response, "4.8")
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, 'href="https://wa.me/919876543210"')
        self.assertContains(response, ">+919876543210</p>")
        self.assertEqual(
            Business(whatsapp="+919876543210").whatsapp_display,
            "+919876543210",
        )
        self.assertContains(response, "Pharmacy")
        self.assertContains(response, "12 Main Road")
        self.assertContains(response, "Near City Park")
        self.assertContains(response, "9:00 AM - 6:00 PM")
        self.assertContains(response, "https://wa.me/919876543210")
        self.assertContains(response, "https://citypharmacy.example")
        self.assertContains(response, "openstreetmap.org/export/embed.html")
        self.assertContains(response, "marker=22.572600000%2C88.363900000")
        self.assertNotContains(response, "Apollo Multispeciality Hospital")

    def test_hides_enquiry_actions_when_business_disables_appointments(self):
        self.business.is_appointment = False
        self.business.save(update_fields=["is_appointment"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertNotContains(
            response,
            reverse("businesses:send-enquiry", args=[self.business.slug]),
        )

    def test_hides_doctor_card_appointment_when_business_disables_appointments(self):
        doctor = Doctor.objects.create(name="Dr. No Booking", business=self.business)
        self.business.is_appointment = False
        self.business.save(update_fields=["is_appointment"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Dr. No Booking")
        self.assertNotContains(
            response,
            reverse("doctors:book-appointment", args=[doctor.slug]),
        )

    def test_displays_alternate_phone_in_contact_information(self):
        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Contact Information")
        self.assertContains(response, "Alternate Phone Number")
        self.assertContains(response, 'href="tel:9876543211"')

    def test_displays_business_tags_without_category_chips(self):
        self.business.tags = "24/7 Open,Home Delivery"
        self.business.save(update_fields=["tags"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "24/7 Open")
        self.assertContains(response, "Home Delivery")
        self.assertNotContains(
            response,
            reverse("businesses:list", kwargs={"slug": self.category.slug}),
        )

    def test_displays_only_published_current_business_updates(self):
        BusinessUpdate.objects.create(
            business=self.business,
            kind=BusinessUpdate.Kind.NEW_DOCTOR,
            title="New physician joined",
            summary="A new physician is now consulting.",
            details="Appointments are available from Monday.",
        )
        BusinessUpdate.objects.create(
            business=self.business,
            title="Draft announcement",
            summary="Not public",
            details="Not public",
            is_published=False,
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "New physician joined")
        self.assertContains(response, 'id="update-detail-sheet"')
        self.assertNotContains(response, "Draft announcement")

    def test_downloads_branded_business_qr_code(self):
        detail_response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )
        qr_url = reverse("businesses:qr-code", kwargs={"slug": self.business.slug})
        self.assertNotContains(detail_response, f'href="{qr_url}"')
        self.assertNotContains(detail_response, ">QR Code</span>")

        response = self.client.get(qr_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{self.business.slug}-mednearby-qr.png"',
        )
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(response.content)) as qr_image:
            self.assertEqual(qr_image.format, "PNG")
            self.assertEqual(qr_image.width, qr_image.height)
            self.assertGreaterEqual(qr_image.width, 300)

    def test_business_detail_renders_image_slider_for_multiple_images(self):
        BusinessImage.objects.bulk_create(
            [
                BusinessImage(
                    business=self.business,
                    image="businesses/first.webp",
                    is_thumbnail=True,
                ),
                BusinessImage(
                    business=self.business,
                    image="businesses/second.webp",
                ),
            ]
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, 'id="business-image-track"')
        self.assertContains(response, "businesses/first.webp")
        self.assertContains(response, "businesses/second.webp")
        self.assertContains(response, 'data-slide-index="0"')
        self.assertContains(response, 'data-slide-index="1"')
        self.assertContains(response, "setInterval(() => showSlide(activeSlide + 1), 4000)")

    def test_business_detail_omits_pagination_for_single_image(self):
        BusinessImage.objects.bulk_create(
            [BusinessImage(business=self.business, image="businesses/only.webp")]
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "businesses/only.webp")
        self.assertNotContains(response, 'id="business-image-dots"')

    def test_displays_assigned_categories_without_placeholder_categories(self):
        diagnostics = Category.objects.create(name="Diagnostic Centre")
        self.business.categories.add(diagnostics)

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Pharmacy")
        self.assertContains(response, "Diagnostic Centre")
        self.assertContains(
            response,
            reverse("businesses:list", kwargs={"slug": diagnostics.slug}),
        )
        self.assertNotContains(response, ">Hospital</")
        self.assertNotContains(response, ">Diagnostics</")

    def test_displays_saved_business_hours_without_placeholder_schedule(self):
        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Monday")
        self.assertContains(response, "9:00 AM - 6:00 PM")
        self.assertContains(response, "(Today)")
        self.assertNotContains(response, "08:00 AM - 10:00 PM")

    def test_action_links_use_available_admin_contact_data(self):
        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, "https://wa.me/919876543210")
        self.assertContains(response, "https://citypharmacy.example")
        self.assertContains(response, "google.com/maps/dir/")
        self.assertNotContains(response, "Appt.")

    def test_whatsapp_share_contains_business_profile_url(self):
        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Share City Pharmacy on WhatsApp")
        self.assertContains(response, "https://api.whatsapp.com/send?text=")
        self.assertContains(response, "Checkout+City+Pharmacy+on+Mednearby+-+http%3A%2F%2Ftestserver")
        self.assertContains(response, "%2Fprovider%2Fcity-pharmacy-near-city-park")
        self.assertContains(response, "Find+verified+medical+services+near+you+and+connect+with+them+easily%21")

    def test_displays_active_business_doctors_without_clinic_info_or_actions(self):
        specialty = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        doctor = Doctor.objects.create(
            business=self.business,
            name="Dr. Test Physician",
            qualification="MBBS, MD",
            gender=Doctor.GenderChoices.MALE,
            fees="500",
            schedule={
                "weekly": [
                    {
                        "weekdays": [0],
                        "note": "Every Monday",
                        "slots": [{"start": "10:00", "end": "12:00"}],
                    }
                ]
            },
        )
        doctor.specialties.add(specialty)
        Doctor.objects.create(
            business=self.business,
            name="Dr. Inactive Physician",
            is_active=False,
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Dr. Test Physician")
        self.assertContains(response, "MBBS, MD")
        self.assertContains(response, "Cardiology")
        self.assertContains(response, "Consultation Fee")
        self.assertContains(response, "₹500")
        self.assertContains(response, "fa-user-doctor")
        self.assertContains(response, "bg-indigo-50")
        self.assertContains(response, "Every Monday")
        self.assertContains(response, "10AM - 12PM")
        self.assertContains(response, "Enquiry")
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, 'data-specialty-filter="all"')
        self.assertContains(
            response,
            f'data-specialty-filter="{specialty.slug}"',
        )
        self.assertContains(
            response,
            f'data-doctor-specialties="{specialty.slug} "',
        )
        self.assertNotContains(response, "Dr. Inactive Physician")
        self.assertNotContains(response, "Visit Clinic")

    def test_location_section_uses_saved_address_and_openstreetmap_coordinates(self):
        self.client.cookies["mednearby_location_lat"] = "22.582600000"
        self.client.cookies["mednearby_location_lng"] = "88.363900000"
        response = self.client.get(reverse("businesses:detail", kwargs={"slug": self.business.slug}))

        self.assertContains(response, "12 Main Road")
        self.assertContains(response, "Near City Park")
        self.assertContains(response, "openstreetmap.org/export/embed.html")
        self.assertContains(response, "marker=22.572600000%2C88.363900000")
        self.assertEqual(response.context["distance_km"], 1.1)
        self.assertContains(response, "1.1 km away from your selected location")
        self.assertNotContains(response, "origin=")
        self.assertContains(response, "destination=22.572600000%2C88.363900000")
        self.assertNotContains(response, "Plot No. 24")
        self.assertNotContains(response, "1.2 km")

    def test_displays_at_most_ten_nearby_similar_businesses(self):
        for number in range(11):
            nearby = Business.objects.create(
                name=f"Similar Pharmacy {number}",
                latitude=str(22.5727 + number * 0.0001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
                is_active=True,
            )
            nearby.categories.add(self.category)

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertEqual(len(response.context["similar_businesses"]), 10)
        self.assertContains(response, "Similar Places Nearby")
        self.assertTrue(
            all(
                item["name"].startswith("Similar Pharmacy")
                for item in response.context["similar_businesses"]
            )
        )
        self.assertNotContains(response, "Sanjeevani Clinic")

    def test_displays_services_from_business_json_field(self):
        self.business.services = [
            "Blood Test",
            "Home Sample Collection",
            "ECG",
            "X-Ray",
        ]
        self.business.save(update_fields=["services"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Services Offered")
        self.assertContains(response, "Blood Test")
        self.assertContains(response, "Home Sample Collection")
        self.assertContains(response, "ECG")
        self.assertContains(response, "X-Ray")
        self.assertNotContains(response, "OPD Consultations")
        self.assertNotContains(response, "Pharmacy 24/7")

    def test_displays_only_assigned_business_facilities(self):
        wifi = Facility.objects.create(
            name="Free Wi-Fi",
            icon="fa-solid fa-wifi",
        )
        Facility.objects.create(
            name="Unassigned Parking",
            icon="fa-solid fa-square-parking",
        )
        self.business.facilities.add(wifi)

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Facilities & Amenities")
        self.assertContains(response, "Free Wi-Fi")
        self.assertContains(response, "fa-solid fa-wifi")
        self.assertNotContains(response, "Unassigned Parking")

    def test_displays_only_enabled_home_service_flags(self):
        self.business.is_home_delivery = True
        self.business.is_home_collection = False
        self.business.save(
            update_fields=["is_home_delivery", "is_home_collection"]
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertContains(response, "Home Delivery")
        self.assertNotContains(response, "Home Collection")

    @override_settings(THUMBNAIL_URL="https://cdn.example/thumbnails/")
    def test_business_thumbnail_uses_configured_prefix_and_default(self):
        self.business.distance_degrees = 0

        self.assertEqual(
            serialize_business(self.business)["thumbnail_url"],
            "https://cdn.example/thumbnails/businesses/default.jpg",
        )

        self.business.thumbnail_url = "clinics/city-pharmacy.jpg"
        self.business.save(update_fields=["thumbnail_url"])
        self.assertEqual(
            serialize_business(self.business)["thumbnail_url"],
            "https://cdn.example/thumbnails/clinics/city-pharmacy.jpg",
        )

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )
        self.assertContains(
            response,
            'src="https://cdn.example/thumbnails/clinics/city-pharmacy.jpg"',
        )
        self.assertContains(
            response,
            '<meta property="og:image" content="https://cdn.example/thumbnails/clinics/city-pharmacy.jpg">',
            html=True,
        )
        self.assertContains(
            response,
            '<meta name="twitter:image" content="https://cdn.example/thumbnails/clinics/city-pharmacy.jpg">',
            html=True,
        )

    def test_draft_business_is_not_public(self):
        self.business.publication_status = Business.PublicationStatus.DRAFT
        self.business.save(update_fields=["publication_status"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertEqual(response.status_code, 404)

    def test_testing_business_is_not_public(self):
        self.business.is_testing = True
        self.business.save(update_fields=["is_testing"])

        response = self.client.get(
            reverse("businesses:detail", kwargs={"slug": self.business.slug})
        )

        self.assertEqual(response.status_code, 404)


class DoctorListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Category.objects.create(
            name="Cardiology",
            label="Cardiologists",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        for number in range(12):
            business = Business.objects.create(
                name=f"Nearby Clinic {number}",
                latitude=str(22.5726 + number * 0.0001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
                is_active=True,
            )
            doctor = Doctor.objects.create(
                name=f"Dr. Nearby {number}",
                business=business,
                qualification="MBBS, MD",
            )
            doctor.specialties.add(cls.specialty)

        far_business = Business.objects.create(
            name="Far Clinic",
            latitude="28.613900000",
            longitude="77.209000000",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        far_doctor = Doctor.objects.create(name="Dr. Far", business=far_business)
        far_doctor.specialties.add(cls.specialty)

        draft_business = Business.objects.create(
            name="Draft Clinic",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.DRAFT,
        )
        draft_doctor = Doctor.objects.create(name="Dr. Draft", business=draft_business)
        draft_doctor.specialties.add(cls.specialty)

    def setUp(self):
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

    def test_initial_page_returns_first_ten_nearest_doctors(self):
        response = self.client.get(
            reverse("doctors:list", kwargs={"slug": self.specialty.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["doctors"]), 10)
        self.assertTrue(response.context["has_more"])
        self.assertEqual(response.context["doctors"][0]["name"], "Dr. Nearby 0")
        self.assertNotContains(response, "Dr. Far")
        self.assertNotContains(response, "Dr. Draft")
        self.assertContains(response, 'data-href="/doctor/dr-nearby-0"')

    def test_ajax_second_page_returns_remaining_doctors(self):
        response = self.client.get(
            reverse("doctors:list", kwargs={"slug": self.specialty.slug}),
            {"page": 2},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["results"]), 2)
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["next_page"], 3)
        self.assertIn("slug", payload["results"][0])

    def test_available_today_filter_shows_zero_count_and_empty_state(self):
        response = self.client.get(
            reverse("doctors:list", kwargs={"slug": self.specialty.slug})
        )

        self.assertEqual(response.context["available_today_count"], 0)
        self.assertContains(response, "Listed Today (0)")
        self.assertContains(response, "No doctors are listed today.")

    def test_page_without_coordinate_cookies_requests_location(self):
        self.client.cookies.clear()

        response = self.client.get(
            reverse("doctors:list", kwargs={"slug": self.specialty.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["location_required"])
        self.assertContains(response, "Select your location")

    def test_non_doctor_category_is_not_available(self):
        category = Category.objects.create(name="Pharmacy")

        response = self.client.get(
            reverse("doctors:list", kwargs={"slug": category.slug})
        )

        self.assertEqual(response.status_code, 404)


class DoctorDetailViewTests(TestCase):
    def setUp(self):
        self.specialty = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        self.business = Business.objects.create(
            name="Heart Clinic",
            address="12 Medical Road",
            phone="9876543210",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        self.doctor = Doctor.objects.create(
            name="Dr. Detail",
            business=self.business,
            qualification="MBBS, MD",
            bio="Experienced heart specialist.",
            fees="700",
        )
        self.doctor.specialties.add(self.specialty)

    def test_displays_doctor_profile_by_slug(self):
        response = self.client.get(
            reverse("doctors:detail", kwargs={"slug": self.doctor.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "directory/doctor_detail.html")
        self.assertContains(response, "Dr. Detail")
        self.assertContains(response, "MBBS, MD")
        self.assertContains(response, "Experienced heart specialist.")
        self.assertContains(response, "Cardiology")
        self.assertContains(response, 'href="tel:9876543210"')
        self.assertContains(response, "Share Dr. Detail on WhatsApp")
        self.assertContains(response, "https://api.whatsapp.com/send?text=")
        self.assertContains(response, "Found+Dr.+Detail%2C+Cardiology+on+Mednearby+-+http%3A%2F%2Ftestserver")
        self.assertContains(response, "%2Fdoctor%2Fdr-detail")
        self.assertContains(response, "Find+verified+medical+services+near+you+and+connect+with+them+easily%21")

    def test_hides_appointment_when_doctors_business_disables_appointments(self):
        self.business.is_appointment = False
        self.business.save(update_fields=["is_appointment"])

        response = self.client.get(
            reverse("doctors:detail", kwargs={"slug": self.doctor.slug})
        )

        self.assertNotContains(
            response,
            reverse("doctors:book-appointment", args=[self.doctor.slug]),
        )

    def test_displays_at_most_ten_nearby_doctors_with_same_specialty(self):
        for number in range(11):
            business = Business.objects.create(
                name=f"Similar Clinic {number}",
                latitude=str(22.5727 + number * 0.00001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
            )
            similar = Doctor.objects.create(
                name=f"Similar Doctor {number}",
                business=business,
                fees="500",
            )
            similar.specialties.add(self.specialty)
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

        response = self.client.get(
            reverse("doctors:detail", kwargs={"slug": self.doctor.slug})
        )

        self.assertEqual(len(response.context["similar_doctors"]), 10)
        self.assertContains(response, "Similar Doctors Nearby")
        self.assertContains(response, "Similar Doctor 0")
        self.assertContains(response, "₹500")
        self.assertNotContains(response, "Similar Doctor 10")

    def test_inactive_doctor_is_not_public(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=["is_active"])

        response = self.client.get(
            reverse("doctors:detail", kwargs={"slug": self.doctor.slug})
        )

        self.assertEqual(response.status_code, 404)
