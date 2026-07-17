from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import identify_hasher, is_password_usable
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    """Create users whose phone number is their login identifier."""

    use_in_migrations = True

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("The phone number is required")

        user = self.model(phone=str(phone).strip(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True")

        return self.create_user(phone, password, **extra_fields)


class User(AbstractUser):
    username = None
    first_name = None
    last_name = None
    email = None

    phone = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=255)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["full_name"]

    def save(self, *args, **kwargs):
        if self.password and is_password_usable(self.password):
            try:
                identify_hasher(self.password)
            except ValueError:
                self.set_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"
