from django.db import models
from django.db.models.functions import Lower

from core.utils import generate_unique_slug


class State(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True, unique=True)

    class Meta:
        verbose_name_plural = "States"
        db_table = "states"
        indexes = [
             models.Index(
                Lower("name"),
                name="state_name_lower_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)
    

class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE)
    slug = models.SlugField(max_length=100, blank=True, unique=True)
    pincode_prefixes = models.CharField(max_length=100, blank=True, null=True, help_text="Comma-separated list of pincode prefixes")

    class Meta:
        verbose_name_plural = "Cities"
        db_table = "cities"
        indexes = [
            models.Index(
                fields=["state", "slug"],
                name="city_state_slug_idx",
            ),
            models.Index(
                Lower("name"),
                name="city_name_lower_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Locality(models.Model):
    class LocalityType(models.TextChoices):
        LOCALITY = "locality", "Locality"
        NEIGHBOURHOOD = "neighbourhood", "Neighbourhood"
        AREA = "area", "Area"
        SUBURB = "suburb", "Suburb"
        TOWN = "town", "Town"
        VILLAGE = "village", "Village"
        WARD = "ward", "Ward"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, unique=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="localities")
    locality_type = models.CharField(
        max_length=20,
        choices=LocalityType.choices,
        default=LocalityType.LOCALITY,
        db_index=True,
    )
    lattitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Localities"
        db_table = "localities"
        indexes = [
             models.Index(
                fields=["city", "slug"],
                name="locality_city_slug_idx",
            ),
            models.Index(
                Lower("name"),
                name="locality_name_lower_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)
