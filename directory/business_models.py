import uuid

import pygeohash as pgh
from django.db import models
from django.utils import timezone

from core.utils import generate_unique_slug

from .models import Category


class Business(models.Model):
    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Review"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True, unique=True)
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="businesses",
        limit_choices_to={"type": Category.Type.BUSINESS_CATEGORY},
    )
    description = models.TextField(max_length=1000, blank=True)
    established_year = models.PositiveSmallIntegerField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    locality = models.ForeignKey(
        "locations.Locality",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    latitude = models.DecimalField(
        max_digits=12,
        decimal_places=9,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=12,
        decimal_places=9,
        null=True,
        blank=True,
    )
    geohash = models.CharField(max_length=12, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    website = models.URLField(max_length=200, blank=True)
    is_testing = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_24_7 = models.BooleanField(default=False)
    is_home_collection = models.BooleanField(default=False)
    is_home_delivery = models.BooleanField(default=False)

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    publication_status = models.CharField(
        max_length=20,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    
    business_hours = models.JSONField(null=True, blank=True)
    services = models.JSONField(null=True, blank=True, default=list)
    thumbnail_url = models.CharField(max_length=200, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Businesses"
        db_table = "businesses"
        indexes = [
            models.Index(
                fields=["locality", "publication_status", "is_active"],
                name="biz_locality_status_idx",
            ),
            models.Index(
                fields=["verification_status", "publication_status", "is_active"],
                name="biz_verify_status_idx",
            ),
            models.Index(
                fields=["publication_status", "published_at"],
                name="biz_published_idx",
            ),
            models.Index(
                fields=["latitude", "longitude", "geohash"],
                name="biz_coordinates_idx",
            ),
            models.Index(fields=["geohash"], name="biz_geohash_idx"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        changed_fields = set()
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
            changed_fields.add("slug")

        if self.latitude is not None and self.longitude is not None:
            self.geohash = pgh.encode(
                latitude=float(self.latitude),
                longitude=float(self.longitude),
                precision=12,
            )
        else:
            self.geohash = None
        changed_fields.add("geohash")

        if (
            self.publication_status == self.PublicationStatus.PUBLISHED
            and self.published_at is None
        ):
            self.published_at = timezone.now()
            changed_fields.add("published_at")

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | changed_fields
        super().save(*args, **kwargs)

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED

    @property
    def is_featured(self):
        return bool(
            self.featured_until
            and self.featured_until > timezone.now()
        )
