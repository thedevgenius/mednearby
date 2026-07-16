from math import cos, radians

from django.db.models import ExpressionWrapper, F, FloatField, Q, Value
from django.db.models.functions import Cast

from .models import Locality


LOCATION_RESULT_LIMIT = 10


def serialize_locality(locality):
    return {
        "id": locality.pk,
        "name": locality.name,
        "slug": locality.slug,
        "city": locality.city.name,
        "state": locality.city.state.name,
        "display_name": f"{locality.name}, {locality.city.name}",
        "lat": float(locality.lattitude) if locality.lattitude is not None else None,
        "lng": float(locality.longitude) if locality.longitude is not None else None,
    }


def search_localities(query, limit=LOCATION_RESULT_LIMIT):
    term = query.strip()
    if len(term) < 3:
        return Locality.objects.none()

    return (
        Locality.objects.select_related("city", "city__state")
        .filter(lattitude__isnull=False, longitude__isnull=False)
        .filter(
            Q(name__icontains=term)
            | Q(city__name__icontains=term)
            | Q(city__state__name__icontains=term)
            | Q(city__state__code__iexact=term)
        )
        .order_by("name", "city__name")[:limit]
    )


def nearest_locality(latitude, longitude):
    """Find the nearest geocoded locality using an equirectangular approximation."""
    latitude = float(latitude)
    longitude = float(longitude)
    longitude_scale = cos(radians(latitude))

    lat = Cast("lattitude", FloatField())
    lng = Cast("longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(longitude_scale)
    distance = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )

    return (
        Locality.objects.filter(lattitude__isnull=False, longitude__isnull=False)
        .select_related("city", "city__state")
        .annotate(distance=distance)
        .order_by("distance")
        .first()
    )
