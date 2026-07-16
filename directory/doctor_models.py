import uuid

from django.db import models

from core.utils import generate_unique_slug

from .business_models import Business
from .models import Category


class Doctor(models.Model):
    class GenderChoices(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        OTHER = "other"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True, unique=True)
    specialties = models.ManyToManyField(
        Category,
        blank=True,
        related_name="doctors",
        limit_choices_to={"type": Category.Type.DOCTOR_SPECIALTY},
    )
    qualification = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=GenderChoices.choices, blank=True)
    bio = models.TextField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    fees = models.CharField(null=True, blank=True)
    schedule = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Doctors"
        db_table = "doctors"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        changed_fields = set()
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
            changed_fields.add("slug")
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | changed_fields
        super().save(*args, **kwargs)


