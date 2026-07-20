from django.test import TestCase
from django.urls import reverse

from directory.models import Business

from .models import User


class UserPasswordSaveTests(TestCase):
    def test_direct_save_hashes_a_raw_password(self):
        user = User(
            phone="9000000001",
            full_name="Direct Save User",
            password="plain-text-password",
        )

        user.save()

        self.assertNotEqual(user.password, "plain-text-password")
        self.assertTrue(user.check_password("plain-text-password"))

    def test_saving_an_existing_hash_does_not_hash_it_again(self):
        user = User.objects.create_user(
            phone="9000000002",
            full_name="Managed User",
            password="safe-password",
        )
        original_hash = user.password

        user.full_name = "Updated Managed User"
        user.save()

        self.assertEqual(user.password, original_hash)
        self.assertTrue(user.check_password("safe-password"))

    def test_unusable_password_remains_unusable(self):
        user = User(phone="9000000003", full_name="No Password User")
        user.set_unusable_password()

        user.save()

        self.assertFalse(user.has_usable_password())


class AccountLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="9000000010",
            full_name="Business Owner",
            password="safe-password",
        )

    def test_login_page_uses_phone_and_password(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "Business login")

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.phone, "password": "safe-password"},
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_invalid_login_shows_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.phone, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid phone number or password")

    def test_login_rejects_non_numeric_or_non_ten_digit_phone(self):
        for phone in ("90000abcde", "90000000101", "900000001"):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": phone, "password": "safe-password"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Enter a valid 10-digit phone number")

    def test_logout_redirects_to_home(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class OwnerDashboardTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="9000000020",
            full_name="First Owner",
            password="safe-password",
        )
        other_owner = User.objects.create_user(
            phone="9000000021",
            full_name="Other Owner",
            password="safe-password",
        )
        self.owned_business = Business.objects.create(
            name="Owned Health Centre",
            owner=self.owner,
            address="12 Health Road",
            landmark="Near City Park",
            pincode="700001",
        )
        self.other_business = Business.objects.create(
            name="Another Owner Clinic", owner=other_owner
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("accounts:dashboard")}',
        )

    def test_dashboard_only_lists_logged_in_users_businesses(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(list(response.context["businesses"]), [self.owned_business])
        self.assertContains(response, self.owned_business.name)
        self.assertContains(
            response,
            "12 Health Road, Near City Park, 700001",
        )
        self.assertNotContains(response, "Address not added")
        self.assertNotContains(response, self.other_business.name)
        self.assertNotContains(response, 'aria-label="Primary navigation"')

    def test_dashboard_business_card_has_qr_download_and_share_actions(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(
            response,
            reverse("businesses:qr-code", kwargs={"slug": self.owned_business.slug}),
        )
        self.assertContains(response, "Download QR")
        self.assertContains(response, "data-share-business")
        self.assertContains(response, "https://api.whatsapp.com/send?text=")
        self.assertNotContains(response, "navigator.share")
        self.assertContains(
            response,
            "View our official business profile on MedNearby for our services, contact details, location, timings, directions, and latest updates",
        )
