from django.db import models

from core.utils import generate_unique_slug


class Category(models.Model):
    class Type(models.TextChoices):
        BUSINESS_CATEGORY = "category", "Business Category"
        DOCTOR_SPECIALTY = "specialty", "Doctor Specialty"

    name = models.CharField(max_length=100, unique=True)
    label = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Plural label for this category",
    )
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.BUSINESS_CATEGORY,
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    aliases = models.CharField(
        max_length=300,
        blank=True,
        help_text="Comma-separated search terms",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="FontAwesome icon class name, for example: fa fa-home",
    )
    color = models.CharField(max_length=10, blank=True, null=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(
        default=False,
        help_text="Show this category prominently on the home page.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Categories"
        db_table = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["type", "slug"],
                name="unique_directory_type_slug",
            ),
            models.UniqueConstraint(
                fields=["type", "name"],
                name="unique_directory_type_name",
            ),
        ]
        indexes = [
            models.Index(
                fields=["type", "is_active", "display_order"],
                name="directory_type_listing_idx",
            ),
            models.Index(fields=["name"], name="category_name_idx"),
            models.Index(fields=["slug"], name="category_slug_idx"),
            models.Index(fields=["aliases"], name="category_alias_idx"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)


# Preserve the existing public import API: from directory.models import ...
from .business_models import (  # noqa: E402, F401
    Ambulance,
    Business,
    BusinessImage,
    BusinessUpdate,
    Facility,
)
from .doctor_models import Doctor  # noqa: E402, F401
