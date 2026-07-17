from django.test import TestCase

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
