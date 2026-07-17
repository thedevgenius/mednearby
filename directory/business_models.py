import uuid
from io import BytesIO
from pathlib import Path

import pygeohash as pgh
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

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
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="businesses",
    )
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
    is_emergency = models.BooleanField(default=False)

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
    facilities = models.ManyToManyField(
        "Facility",
        blank=True,
        related_name="businesses",
    )

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
        slug_source = " ".join(
            part.strip() for part in (self.name, self.landmark) if part and part.strip()
        )
        self.slug = generate_unique_slug(self, slug_source, fallback="business")
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


class BusinessImage(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="businesses",
        validators=[
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            )
        ],
    )
    is_thumbnail = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Business Images"
        db_table = "business_images"
        constraints = [
            models.UniqueConstraint(
                fields=("business",),
                condition=Q(is_thumbnail=True),
                name="one_thumbnail_per_business",
            )
        ]

    def _prepare_webp_image(self):
        if not self.image or self.image._committed:
            return

        try:
            self.image.seek(0)
            with Image.open(self.image) as source:
                source.verify()
            self.image.seek(0)
            with Image.open(self.image) as source:
                processed = ImageOps.exif_transpose(source)
                if processed.width > 768:
                    height = max(1, round(processed.height * 768 / processed.width))
                    processed = processed.resize(
                        (768, height),
                        Image.Resampling.LANCZOS,
                    )
                if processed.mode not in ("RGB", "RGBA"):
                    processed = processed.convert(
                        "RGBA" if "transparency" in processed.info else "RGB"
                    )

                output = BytesIO()
                processed.save(
                    output,
                    format="WEBP",
                    quality=82,
                    method=6,
                    optimize=True,
                )
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(
                {"image": "Upload a valid JPG, PNG, or WebP image file."}
            ) from exc

        output.seek(0)
        filename = f"{Path(self.image.name).stem}.webp"
        self.image = ContentFile(output.read(), name=filename)

    @transaction.atomic
    def save(self, *args, **kwargs):
        previous = None
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "image", "is_thumbnail"
            ).first()

        self._prepare_webp_image()

        if self.is_thumbnail:
            type(self).objects.filter(
                business_id=self.business_id,
                is_thumbnail=True,
            ).exclude(pk=self.pk).update(is_thumbnail=False)

        super().save(*args, **kwargs)

        if self.is_thumbnail:
            Business.objects.filter(pk=self.business_id).update(
                thumbnail_url=self.image.name
            )
        elif previous and previous["is_thumbnail"]:
            Business.objects.filter(
                pk=self.business_id,
                thumbnail_url=previous["image"],
            ).update(thumbnail_url=None)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        business_id = self.business_id
        image_name = self.image.name
        was_thumbnail = self.is_thumbnail
        result = super().delete(*args, **kwargs)
        if was_thumbnail:
            Business.objects.filter(
                pk=business_id,
                thumbnail_url=image_name,
            ).update(thumbnail_url=None)
        return result

    def __str__(self):
        return f"{self.business.name} - {self.image}"


class Ambulance(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="ambulances",
    )
    phone = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    is_24_7 = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Ambulances"
        db_table = "ambulances"

    def __str__(self):
        return f"{self.business.name} - {self.phone}"


class Facility(models.Model):
    name = models.CharField(max_length=255)
    icon = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Facilities"
        db_table = "facilities"

    def __str__(self):
        return self.name
