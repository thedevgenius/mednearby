from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from directory.models import Ambulance, Business, BusinessUpdate, Category, Doctor


class AboutUsViewTests(SimpleTestCase):
    def test_about_us_page_uses_expected_template(self):
        response = self.client.get(reverse("core:about-us"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/about_us.html")


class NotFoundPageTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_custom_404_page_has_recovery_actions(self):
        response = self.client.get("/this-page-does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "This page wandered off", status_code=404)
        self.assertContains(response, reverse("core:home"), status_code=404)
        self.assertContains(response, reverse("doctors:specialties"), status_code=404)
        self.assertContains(
            response,
            'data-bottom-sheet-target="#search-sheet"',
            status_code=404,
        )


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

    def test_home_page_registers_pwa_assets(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "manifest.webmanifest")
        self.assertContains(response, "navigator.serviceWorker.register")
        self.assertContains(response, reverse("core:service-worker"))
        self.assertContains(response, "/static/icons/icon-192x192.png")
        self.assertContains(response, 'id="pwa-install-cta"')
        self.assertContains(response, 'id="pwa-install-button"')

    def test_serves_root_scoped_javascript_without_http_cache(self):
        response = self.client.get(reverse("core:service-worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertContains(response, 'const CACHE_NAME = "mednearby-static-v2"')
        self.assertContains(response, "/static/css/style.css")
        self.assertContains(response, "/static/icons/icon-192x192.png")
        self.assertContains(response, "/static/icons/icon-512x512.png")

    def test_home_page_includes_bottom_navigation(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, 'aria-label="Primary navigation"')
        self.assertContains(response, ">Saved</span>")
        self.assertNotContains(response, ">Admin</span>")
        self.assertNotContains(response, ">Tasks</span>")

    def test_superuser_bottom_navigation_includes_admin_and_tasks(self):
        user = get_user_model().objects.create_superuser(
            phone="9000000099",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, f'href="{reverse("admin:index")}"')
        self.assertContains(response, f'href="{reverse("core:internal-tasks")}"')
        self.assertContains(response, ">Admin</span>")
        self.assertContains(response, ">Tasks</span>")


class SavedViewTests(SimpleTestCase):
    def test_saved_page_uses_local_storage_ui(self):
        response = self.client.get(reverse("core:saved"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/saved.html")
        self.assertContains(response, 'id="saved-doctors"')
        self.assertContains(response, 'id="saved-businesses"')
        self.assertContains(response, "js/saved-items.js")


class SavedItemsViewTests(TestCase):
    def test_resolves_published_items_by_slug(self):
        category = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
        )
        business_category = Category.objects.create(name="Clinic")
        business = Business.objects.create(
            name="Saved Clinic",
            address="10 Health Street",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        business.categories.add(business_category)
        doctor = Doctor.objects.create(
            business=business,
            name="Dr. Saved",
            qualification="MBBS",
            fees="600",
        )
        doctor.specialties.add(category)

        response = self.client.get(
            reverse("core:saved-items"),
            {"doctor": doctor.slug, "business": business.slug},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["doctors"][0]["slug"], doctor.slug)
        self.assertEqual(response.json()["doctors"][0]["specialty"], "Cardiology")
        self.assertEqual(response.json()["doctors"][0]["fees"], "600")
        self.assertEqual(response.json()["businesses"][0]["slug"], business.slug)
        self.assertEqual(response.json()["businesses"][0]["category"], "Clinic")


class CategoriesViewTests(TestCase):
    def test_lists_active_categories_with_subcategories(self):
        parent = Category.objects.create(name="Diagnostics")
        child = Category.objects.create(name="Blood Tests", parent=parent)
        specialty = Category.objects.create(
            name="Cardiology",
            type=Category.Type.DOCTOR_SPECIALTY,
            synonyms="Heart doctor, Heart specialist",
        )
        Category.objects.create(name="Hidden Category", is_active=False)

        response = self.client.get(reverse("core:categories"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/categories.html")
        self.assertContains(response, "Diagnostics")
        self.assertContains(response, "Blood Tests")
        self.assertContains(response, "Cardiology")
        self.assertContains(response, "Heart doctor, Heart specialist")
        self.assertContains(response, reverse("businesses:list", kwargs={"slug": child.slug}))
        self.assertContains(response, reverse("doctors:list", kwargs={"slug": specialty.slug}))
        self.assertNotContains(response, "Hidden Category")

    def test_explore_nav_links_to_categories_and_is_active(self):
        response = self.client.get(reverse("core:categories"))

        self.assertContains(response, f'href="{reverse("core:categories")}"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, 'href="#business-categories"')
        self.assertContains(response, 'href="#doctor-specialties"')

    def test_orders_categories_and_children_by_display_order_then_name(self):
        later = Category.objects.create(name="A Later Parent", display_order=2)
        earlier = Category.objects.create(name="Z Earlier Parent", display_order=1)
        Category.objects.create(name="Z Child", parent=earlier, display_order=2)
        Category.objects.create(name="B Child", parent=earlier, display_order=1)
        Category.objects.create(name="A Child", parent=earlier, display_order=1)

        response = self.client.get(reverse("core:categories"))
        content = response.content.decode()

        self.assertLess(content.index(earlier.name), content.index(later.name))
        self.assertLess(content.index("A Child"), content.index("B Child"))
        self.assertLess(content.index("B Child"), content.index("Z Child"))


class NearbyUpdatesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(
            name="Community Clinic",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        cls.update = BusinessUpdate.objects.create(
            business=cls.business,
            kind=BusinessUpdate.Kind.OFFER,
            title="Free health check",
            summary="A complimentary health check this weekend.",
            details="Visit the clinic between 9 AM and 1 PM.",
        )
        BusinessUpdate.objects.create(
            business=cls.business,
            title="Hidden update",
            summary="Not public",
            details="Not public",
            is_published=False,
        )

    def setUp(self):
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

    def test_home_shows_nearby_published_updates_and_detail_sheet(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(list(response.context["nearby_updates"]), [self.update])
        self.assertContains(response, "Free health check")
        self.assertContains(response, 'id="update-detail-sheet"')
        self.assertNotContains(response, "Hidden update")

    def test_updates_page_lists_nearby_updates(self):
        response = self.client.get(reverse("core:updates"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Free health check")
        self.assertContains(response, "View more")

    def test_updates_page_requests_location_when_missing(self):
        self.client.cookies.clear()
        response = self.client.get(reverse("core:updates"))

        self.assertTrue(response.context["location_required"])
        self.assertContains(response, "Choose a location")

    def test_updates_page_loads_twenty_then_returns_more_with_ajax(self):
        for number in range(24):
            BusinessUpdate.objects.create(
                business=self.business,
                title=f"Update {number}",
                summary=f"Summary {number}",
                details=f"Details {number}",
            )

        response = self.client.get(reverse("core:updates"))

        self.assertEqual(len(response.context["updates"]), 20)
        self.assertTrue(response.context["has_more"])
        self.assertContains(response, 'id="load-more-updates"')
        self.assertContains(response, "bg-gradient-to-br")

        ajax_response = self.client.get(
            reverse("core:updates"),
            {"page": 2},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        payload = ajax_response.json()
        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(payload["html"].count('class="update-card '), 5)
        self.assertIn("from-amber-50/90", payload["html"])
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["next_page"], 3)


class HomeFeaturedSpecialtyTests(TestCase):
    def test_home_lists_only_active_featured_doctor_specialties(self):
        featured = Category.objects.create(
            name="Cardiology",
            label="Cardiologists",
            type=Category.Type.DOCTOR_SPECIALTY,
            icon="fa-solid fa-heart-pulse",
            color="rose-500",
            synonyms="Heart doctor, Heart specialist",
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
        self.assertContains(response, "Heart doctor, Heart specialist")
        self.assertContains(response, "text-rose-500")
        self.assertContains(response, "fa-solid fa-heart-pulse")
        self.assertNotContains(response, "Neurology")
        self.assertNotContains(response, "Inactive Featured")


class HomeAvailableDoctorsTests(TestCase):
    def test_home_lists_at_most_ten_nearby_doctors(self):
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

    def test_home_includes_nearby_doctor_not_available_today(self):
        business = Business.objects.create(
            name="Local Clinic",
            latitude="22.572600000",
            longitude="88.363900000",
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        Doctor.objects.create(name="Doctor Without Today's Schedule", business=business)
        self.client.cookies["mednearby_location_lat"] = "22.5726"
        self.client.cookies["mednearby_location_lng"] = "88.3639"

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "Doctor Without Today&#x27;s Schedule")
        self.assertContains(response, "Schedule not listed")

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
        self.assertContains(response, "Closed Nearby Business")
        self.assertContains(response, "Closed")


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
        self.assertContains(response, "Download Business QR")

    def test_staff_user_can_download_selected_business_qr(self):
        user = get_user_model().objects.create_user(
            phone="9000000003",
            password="test-password",
            is_staff=True,
        )
        business = Business.objects.create(name="QR Task Clinic")
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "core:internal-business-qr-code",
                kwargs={"business_id": business.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{business.slug}-mednearby-qr.png"',
        )
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_internal_business_qr_requires_staff_login(self):
        business = Business.objects.create(name="Private QR Clinic")

        response = self.client.get(
            reverse(
                "core:internal-business-qr-code",
                kwargs={"business_id": business.pk},
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


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

    def test_business_hours_builder_has_copy_above_control(self):
        response = self.client.get(
            reverse("core:business-hours-task", kwargs={"business_id": self.business.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copy above")
        self.assertContains(response, 'state[String(index - 1)].map')

    def test_business_services_builder_saves_normalized_json(self):
        response = self.client.post(
            reverse("core:business-services-task", kwargs={"business_id": self.business.pk}),
            {"services": '["Blood Test", " Home Delivery ", "blood test"]'},
        )

        self.business.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.business.services, ["Blood Test", "Home Delivery"])
        self.assertContains(response, "updated successfully")

    def test_business_services_builder_shows_common_and_existing_services(self):
        self.business.services = ["Custom Nursing"]
        self.business.save(update_fields=["services"])

        response = self.client.get(
            reverse("core:business-services-task", kwargs={"business_id": self.business.pk})
        )

        self.assertContains(response, "Doctor Consultation")
        self.assertContains(response, "Home Sample Collection")
        self.assertContains(response, "Blood Pressure Check")
        self.assertContains(response, "Injection Administration")
        self.assertContains(response, 'data-common-service="Blood Test"')
        self.assertContains(response, "Custom Nursing")
        self.assertContains(response, "Save Business Services")

    def test_business_services_builder_rejects_invalid_json_structure(self):
        response = self.client.post(
            reverse("core:business-services-task", kwargs={"business_id": self.business.pk}),
            {"services": '{"name":"Blood Test"}'},
        )

        self.assertEqual(response.status_code, 400)

    def test_business_tags_builder_saves_comma_separated_tags(self):
        response = self.client.post(
            reverse("core:business-tags-task", kwargs={"business_id": self.business.pk}),
            {"tags": '["24/7 Open", " Home Delivery ", "24/7 open"]'},
        )

        self.business.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.business.tags, "24/7 Open,Home Delivery")
        self.assertEqual(self.business.tag_list, ["24/7 Open", "Home Delivery"])

    def test_business_tags_builder_shows_common_tags(self):
        response = self.client.get(
            reverse("core:business-tags-task", kwargs={"business_id": self.business.pk})
        )

        self.assertContains(response, 'data-common-tag="24/7 Open"')
        self.assertContains(response, "Wheelchair Accessible")
        self.assertContains(response, "Save Business Tags")

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

        response = self.client.get(
            reverse("core:business-tags-task", kwargs={"business_id": self.business.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

        response = self.client.get(
            reverse("core:business-services-task", kwargs={"business_id": self.business.pk})
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
