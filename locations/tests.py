from django.test import TestCase
from django.urls import reverse

from directory.models import Category

from .models import City, Locality, State


class UniqueSlugTests(TestCase):
    def test_category_uses_counter_for_colliding_slug(self):
        first = Category.objects.create(name="Heart Care")
        second = Category.objects.create(name="Heart-care")

        self.assertEqual(first.slug, "heart-care")
        self.assertEqual(second.slug, "heart-care-2")

    def test_all_location_models_generate_slugs(self):
        state = State.objects.create(name="West Bengal", code="WB")
        city = City.objects.create(name="Kolkata", state=state)
        locality = Locality.objects.create(name="Salt Lake", city=city)

        self.assertEqual(state.slug, "west-bengal")
        self.assertEqual(city.slug, "kolkata")
        self.assertEqual(locality.slug, "salt-lake")

    def test_location_slug_collision_uses_counter(self):
        first = State.objects.create(name="New Delhi", code="DL")
        second = State.objects.create(name="New-Delhi", code="ND")

        self.assertEqual(first.slug, "new-delhi")
        self.assertEqual(second.slug, "new-delhi-2")

    def test_regenerating_slug_on_existing_instance_excludes_itself(self):
        state = State.objects.create(name="Maharashtra", code="MH")
        state.slug = ""
        state.save()

        self.assertEqual(state.slug, "maharashtra")

    def test_counter_keeps_slug_within_field_max_length(self):
        long_name = "A" * 120
        first = State.objects.create(name=long_name, code="A1")
        second = State.objects.create(name=long_name, code="A2")

        self.assertEqual(len(first.slug), 100)
        self.assertEqual(len(second.slug), 100)
        self.assertTrue(second.slug.endswith("-2"))


class LocalityApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        state = State.objects.create(name="West Bengal", code="WB")
        city = City.objects.create(name="Kolkata", state=state)
        cls.nearby = Locality.objects.create(
            name="Salt Lake",
            city=city,
            lattitude="22.586700",
            longitude="88.417100",
        )
        Locality.objects.create(
            name="Park Street",
            city=city,
            lattitude="22.553000",
            longitude="88.352500",
        )
        Locality.objects.create(name="Unmapped Area", city=city)

    def test_search_returns_locality_context_and_coordinates(self):
        response = self.client.get(
            reverse("locations:locality-search"),
            {"q": "Salt"},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["display_name"], "Salt Lake, Kolkata")
        self.assertEqual(result["state"], "West Bengal")
        self.assertEqual(result["lat"], 22.5867)
        self.assertEqual(result["lng"], 88.4171)

    def test_search_requires_at_least_three_characters(self):
        response = self.client.get(
            reverse("locations:locality-search"),
            {"q": "Sa"},
        )

        self.assertEqual(response.json()["results"], [])

    def test_search_excludes_localities_without_coordinates(self):
        response = self.client.get(
            reverse("locations:locality-search"),
            {"q": "Unmapped"},
        )

        self.assertEqual(response.json()["results"], [])

    def test_nearest_endpoint_returns_closest_geocoded_locality(self):
        response = self.client.get(
            reverse("locations:nearest-locality"),
            {"lat": "22.585", "lng": "88.416"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["id"], self.nearby.pk)

    def test_nearest_endpoint_rejects_invalid_coordinates(self):
        response = self.client.get(
            reverse("locations:nearest-locality"),
            {"lat": "north", "lng": "88.4"},
        )

        self.assertEqual(response.status_code, 400)

    def test_nearest_endpoint_rejects_out_of_range_coordinates(self):
        response = self.client.get(
            reverse("locations:nearest-locality"),
            {"lat": "91", "lng": "88.4"},
        )

        self.assertEqual(response.status_code, 400)
