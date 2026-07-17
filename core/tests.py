from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from directory.models import Ambulance, Business, Category, Doctor


class HomeViewTests(TestCase):
    def test_home_page_uses_expected_template(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_home_page_includes_reusable_bottom_sheet(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "window.openBottomSheet")
        self.assertContains(response, "window.closeBottomSheet")
        self.assertContains(response, 'id="location-sheet"')
        self.assertContains(response, "js/location-picker.js")


class HomeFeaturedSpecialtyTests(TestCase):
    def test_home_lists_only_active_featured_doctor_specialties(self):
        featured = Category.objects.create(
            name="Cardiology",
            label="Cardiologists",
            type=Category.Type.DOCTOR_SPECIALTY,
            icon="fa-solid fa-heart-pulse",
            color="rose-500",
            is_featured=True,
        )
        Category.objects.create(
            name="Neurology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        Category.objects.create(
            name="Inactive Featured",
            type=Category.Type.DOCTOR_SPECIALTY,
            is_active=False,
            is_featured=True,
        )

        response = self.client.get(reverse("core:home"))

        self.assertQuerySetEqual(response.context["featured_specialties"], [featured])
        self.assertContains(response, "Cardiologists")
        self.assertContains(response, "text-rose-500")
        self.assertContains(response, "fa-solid fa-heart-pulse")
        self.assertNotContains(response, "Neurology")
        self.assertNotContains(response, "Inactive Featured")


class HomeAvailableDoctorsTests(TestCase):
    def test_home_lists_at_most_ten_nearby_doctors_available_today(self):
        weekday = timezone.localtime().weekday()
        schedule = {
            "weekly": [
                {
                    "weekdays": [weekday],
                    "slots": [{"start": "00:00", "end": "23:59"}],
                }
            ]
        }
        for number in range(11):
            business = Business.objects.create(
                name=f"Clinic {number}",
                latitude=str(22.5726 + number * 0.00001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
            )
            Doctor.objects.create(
                name=f"Available Doctor {number}",
                business=business,
                schedule=schedule,
            )

        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"
        response = self.client.get(reverse("core:home"))

        self.assertEqual(len(response.context["available_doctors"]), 10)
        self.assertContains(response, "Doctors Near You")
        self.assertContains(response, "Available Doctor 0")
        self.assertContains(response, 'data-href="/doctor/available-doctor-0"')
        self.assertNotContains(response, "Available Doctor 10")

    def test_home_hides_available_doctors_without_a_selected_location(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["available_doctors"], [])
        self.assertEqual(response.context["nearby_businesses"], [])
        self.assertNotContains(response, "Doctors Near You")


class HomeNearbyBusinessesTests(TestCase):
    def test_home_lists_at_most_ten_nearby_businesses(self):
        category = Category.objects.create(name="Pharmacy", icon="fa-solid fa-capsules")
        weekday = timezone.localtime().weekday()
        open_hours = {
            str(weekday): [{"opens_at": "00:00", "closes_at": "23:59"}]
        }
        for number in range(11):
            business = Business.objects.create(
                name=f"Nearby Business {number}",
                latitude=str(22.5726 + number * 0.00001),
                longitude="88.363900000",
                business_hours=open_hours,
                publication_status=Business.PublicationStatus.PUBLISHED,
            )
            business.categories.add(category)
        closed = Business.objects.create(
            name="Closed Nearby Business",
            latitude="22.572600001",
            longitude="88.363900000",
            business_hours={},
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        closed.categories.add(category)

        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"
        response = self.client.get(reverse("core:home"))

        self.assertEqual(len(response.context["nearby_businesses"]), 10)
        self.assertContains(response, "Businesses Near You")
        self.assertContains(response, "Nearby Business 0")
        self.assertNotContains(response, "Nearby Business 10")
        self.assertNotContains(response, "Closed Nearby Business")


class InternalTasksViewTests(TestCase):
    def test_anonymous_user_is_redirected_to_admin_login(self):
        response = self.client.get(reverse("core:internal-tasks"))

        self.assertRedirects(
            response,
            f"/admin/login/?next={reverse('core:internal-tasks')}",
        )

    def test_staff_user_can_open_internal_tasks_page(self):
        user = get_user_model().objects.create_user(
            phone="9000000001",
            password="test-password",
            full_name="Staff User",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:internal-tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/internal_tasks.html")
        self.assertContains(response, "Internal Tasks")


class InternalScheduleTaskViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            phone="9000000002", password="test-password", is_staff=True
        )
        self.business = Business.objects.create(name="Schedule Clinic")
        self.doctor = Doctor.objects.create(name="Dr. Schedule", business=self.business)
        self.client.force_login(self.user)

    def test_business_hours_builder_saves_json(self):
        hours = '{"0":[{"opens_at":"09:00","closes_at":"18:00"}]}'
        response = self.client.post(
            reverse("core:business-hours-task", kwargs={"business_id": self.business.pk}),
            {"business_hours": hours},
        )

        self.business.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.business.business_hours["0"][0]["opens_at"], "09:00")
        self.assertContains(response, "updated successfully")

    def test_doctor_schedule_builder_saves_json(self):
        schedule = '{"weekly":[{"weekdays":[0],"slots":[{"start":"09:00","end":"13:00"}],"note":"Available every Monday"}],"monthly_weekday":[],"monthly_dates":[]}'
        response = self.client.post(
            reverse("core:doctor-schedule-task", kwargs={"doctor_id": self.doctor.pk}),
            {"schedule": schedule},
        )

        self.doctor.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.doctor.schedule["weekly"][0]["note"], "Available every Monday")
        self.assertContains(response, "updated successfully")

    def test_builders_require_staff_login(self):
        self.client.logout()

        response = self.client.get(
            reverse("core:business-hours-task", kwargs={"business_id": self.business.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
from django.test import TestCase
from django.urls import reverse


class EmergencyViewTests(TestCase):
    def test_emergency_page_uses_blank_template(self):
        response = self.client.get(reverse("core:emergency"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/emergency.html")

    def test_emergency_lists_at_most_ten_nearby_active_ambulances(self):
        for number in range(11):
            business = Business.objects.create(
                name=f"Ambulance Provider {number}",
                latitude=str(22.5726 + number * 0.00001),
                longitude="88.363900000",
                publication_status=Business.PublicationStatus.PUBLISHED,
            )
            Ambulance.objects.create(
                business=business,
                phone=f"9000000{number:03d}",
            )

        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"
        response = self.client.get(reverse("core:emergency"))

        self.assertEqual(len(response.context["ambulances"]), 10)
        self.assertContains(response, "Ambulance Provider 0")
        self.assertNotContains(response, "Ambulance Provider 10")
        self.assertContains(response, 'href="tel:9000000000"')

    def test_emergency_requests_location_when_not_selected(self):
        response = self.client.get(reverse("core:emergency"))

        self.assertTrue(response.context["location_required"])
        self.assertContains(response, "Select your location")


class AmbulanceListViewTests(TestCase):
    def test_lists_ambulances_ordered_by_business_distance(self):
        farther_business = Business.objects.create(
            name="Farther Ambulance",
            latitude="22.582600000",
            longitude="88.363900000",
            address="Farther Road",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        nearer_business = Business.objects.create(
            name="Nearer Ambulance",
            latitude="22.572700000",
            longitude="88.363900000",
            address="Nearby Road",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        Ambulance.objects.create(business=farther_business, phone="9111111111")
        Ambulance.objects.create(
            business=nearer_business,
            phone="9222222222",
            is_24_7=True,
        )
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

        response = self.client.get(reverse("core:ambulances"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/ambulance_list.html")
        self.assertEqual(
            [item["business"] for item in response.context["ambulances"]],
            ["Nearer Ambulance", "Farther Ambulance"],
        )
        self.assertContains(response, "Nearby Road")
        self.assertContains(response, "Available 24x7")
        self.assertNotContains(response, "Directions")
