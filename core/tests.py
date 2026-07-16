from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from directory.models import Business, Category, Doctor


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
