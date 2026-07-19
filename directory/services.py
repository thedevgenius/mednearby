import calendar
from copy import deepcopy
from datetime import datetime, timedelta
from math import cos, radians
from zoneinfo import ZoneInfo

import pygeohash as pgh
from django.conf import settings
from django.db.models import ExpressionWrapper, F, FloatField
from django.db.models import Q
from django.db.models import Value
from django.db.models.functions import Cast
from django.utils import timezone

from .models import Ambulance, Business, BusinessUpdate, Category, Doctor


SEARCH_RESULT_LIMIT = 10
BUSINESS_PAGE_SIZE = 10
DOCTOR_PAGE_SIZE = 10
MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
KOLKATA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def published_updates():
    """Return updates that are published and within their optional display window."""
    now = timezone.now()
    return BusinessUpdate.objects.filter(
        is_published=True,
        business__is_testing=False,
        business__is_active=True,
        business__publication_status=Business.PublicationStatus.PUBLISHED,
    ).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    )


def nearby_updates(latitude, longitude, limit=None):
    """Return current business updates ordered by business proximity and recency."""
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(business__geohash__startswith=prefix)

    lat = Cast("business__latitude", FloatField())
    lng = Cast("business__longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    queryset = (
        published_updates()
        .filter(
            business__latitude__isnull=False,
            business__longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("business", "business__locality", "business__locality__city")
        .annotate(distance_degrees=distance)
        .order_by("distance_degrees", "-created_at", "-id")
    )
    return queryset[:limit] if limit is not None else queryset


def search_categories(query, limit=SEARCH_RESULT_LIMIT):
    """Return active categories matching a user-entered search term."""
    term = query.strip()
    if not term:
        return Category.objects.none()

    return (
        Category.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=term)
            | Q(label__icontains=term)
            | Q(slug__icontains=term)
            | Q(aliases__icontains=term)
        )
        .only("name", "label", "slug", "type", "icon", "display_order")
        .order_by("display_order", "name")
    )[:limit]


def serialize_category(category):
    destination = "doctors" if category.type == Category.Type.DOCTOR_SPECIALTY else "category"
    return {
        "name": category.name,
        "label": category.label or category.name,
        "slug": category.slug,
        "type": category.type,
        "type_label": category.get_type_display(),
        "icon": category.icon,
        "url": f"/{destination}/{category.slug}",
    }


def neighboring_geohashes(geohash):
    top = pgh.get_adjacent(geohash, "top")
    bottom = pgh.get_adjacent(geohash, "bottom")
    return {
        geohash,
        top,
        bottom,
        pgh.get_adjacent(geohash, "left"),
        pgh.get_adjacent(geohash, "right"),
        pgh.get_adjacent(top, "left"),
        pgh.get_adjacent(top, "right"),
        pgh.get_adjacent(bottom, "left"),
        pgh.get_adjacent(bottom, "right"),
    }


def businesses_near_category(category, latitude, longitude, page=1):
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(geohash__startswith=prefix)

    lat = Cast("latitude", FloatField())
    lng = Cast("longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )

    queryset = (
        Business.objects.filter(
            categories=category,
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("locality", "locality__city")
        .prefetch_related("categories")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
    )
    total_count = queryset.count()
    start = (page - 1) * BUSINESS_PAGE_SIZE
    items = list(queryset[start : start + BUSINESS_PAGE_SIZE + 1])
    return items[:BUSINESS_PAGE_SIZE], len(items) > BUSINESS_PAGE_SIZE, total_count


def businesses_nearby(latitude, longitude, limit=10):
    """Return the nearest currently open, active, published businesses."""
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(geohash__startswith=prefix)

    lat = Cast("latitude", FloatField())
    lng = Cast("longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    businesses = (
        Business.objects.filter(
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("locality", "locality__city")
        .prefetch_related("categories")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
    )
    open_businesses = []
    for business in businesses.iterator(chunk_size=100):
        serialized = serialize_business(business)
        if serialized["is_open"]:
            open_businesses.append(serialized)
            if len(open_businesses) == limit:
                break
    return open_businesses


def ambulances_nearby(latitude, longitude, limit=None):
    """Return active ambulances ordered by their business location."""
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(business__geohash__startswith=prefix)

    lat = Cast("business__latitude", FloatField())
    lng = Cast("business__longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    queryset = (
        Ambulance.objects.filter(
            is_active=True,
            business__is_testing=False,
            business__is_active=True,
            business__publication_status=Business.PublicationStatus.PUBLISHED,
            business__latitude__isnull=False,
            business__longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("business", "business__locality", "business__locality__city")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
    )
    if limit is not None:
        queryset = queryset[:limit]
    return [serialize_ambulance(ambulance) for ambulance in queryset]


def serialize_ambulance(ambulance):
    business = ambulance.business
    address_parts = [
        business.address,
        business.landmark,
        business.locality.name if business.locality else "",
        business.locality.city.name if business.locality and business.locality.city else "",
        business.pincode,
    ]
    return {
        "business": business.name,
        "business_slug": business.slug,
        "phone": ambulance.phone,
        "is_24_7": ambulance.is_24_7,
        "distance_km": round((ambulance.distance_degrees ** 0.5) * 111.195, 1),
        "address": ", ".join(
            part.strip() for part in address_parts if part and part.strip()
        ),
        "latitude": business.latitude,
        "longitude": business.longitude,
    }


def similar_businesses_nearby(business, limit=10):
    """Return nearby published businesses sharing a category with a business."""
    if business.latitude is None or business.longitude is None:
        return []

    categories = list(business.categories.all())
    if not categories:
        return []

    latitude = float(business.latitude)
    longitude = float(business.longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(geohash__startswith=prefix)

    lat = Cast("latitude", FloatField())
    lng = Cast("longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    nearby = (
        Business.objects.filter(
            categories__in=categories,
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .exclude(pk=business.pk)
        .filter(geohash_filter)
        .select_related("locality", "locality__city")
        .prefetch_related("categories")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
        .distinct()[:limit]
    )
    return [serialize_business(item) for item in nearby]


def _parse_time(value):
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        return None
    return parsed.hour * 60 + parsed.minute


def _format_time(minutes):
    minutes %= MINUTES_PER_DAY
    hour, minute = divmod(minutes, 60)
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d}{suffix}" if minute else f"{display_hour}{suffix}"


def business_thumbnail_url(business):
    thumbnail_name = (
        (business.thumbnail_url or "").strip() or "businesses/default.jpg"
    )
    return f"{settings.THUMBNAIL_URL.rstrip('/')}/{thumbnail_name.lstrip('/')}"


def business_open_status(business_hours, now=None):
    """Compare saved wall-clock hours with the current time in Kolkata."""
    current = timezone.localtime(now or timezone.now(), KOLKATA_TIMEZONE)
    current_minute = (
        current.weekday() * MINUTES_PER_DAY
        + current.hour * 60
        + current.minute
    )
    intervals = []
    hours = business_hours if isinstance(business_hours, dict) else {}
    for weekday in range(7):
        slots = hours.get(str(weekday), [])
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            opens_at = _parse_time(slot.get("opens_at"))
            closes_at = _parse_time(slot.get("closes_at"))
            if opens_at is None or closes_at is None or opens_at == closes_at:
                continue
            start = weekday * MINUTES_PER_DAY + opens_at
            end = weekday * MINUTES_PER_DAY + closes_at
            if end <= start:
                end += MINUTES_PER_DAY
            for offset in (-MINUTES_PER_WEEK, 0, MINUTES_PER_WEEK):
                intervals.append((start + offset, end + offset))

    if not intervals:
        return False, "Hours unavailable"

    containing = [interval for interval in intervals if interval[0] <= current_minute < interval[1]]
    if containing:
        _, closes_at = min(containing, key=lambda interval: interval[1])
        if closes_at - current_minute < 60:
            return True, f"Closes at {_format_time(closes_at)}"
        return True, ""

    future_starts = [start for start, _ in intervals if start > current_minute]
    if not future_starts:
        return False, ""

    next_start = min(future_starts)
    days_ahead = next_start // MINUTES_PER_DAY - current.weekday()
    if days_ahead == 0:
        prefix = "Open"
    elif days_ahead == 1:
        prefix = "Open Tomorrow"
    else:
        prefix = f"Open {WEEKDAY_NAMES[next_start // MINUTES_PER_DAY % 7]}"
    return False, f"{prefix} {_format_time(next_start)}"


def serialize_business(business, now=None):
    distance_km = (business.distance_degrees ** 0.5) * 111.195
    is_open, open_status = business_open_status(business.business_hours, now=now)
    categories = list(business.categories.all())
    locality = business.locality
    address_parts = [
        business.address,
        business.landmark,
        locality.name if locality else "",
        locality.city.name if locality and locality.city else "",
        business.pincode,
    ]
    full_address = ", ".join(part.strip() for part in address_parts if part and part.strip())
    return {
        "id": str(business.pk),
        "name": business.name,
        "slug": business.slug,
        "description": business.description,
        "address": business.address,
        "landmark": business.landmark,
        "locality": locality.name if locality else "",
        "city": locality.city.name if locality and locality.city else "",
        "pincode": business.pincode,
        "full_address": full_address or "Address unavailable",
        "categories": [category.name for category in categories],
        "tags": business.tag_list,
        "icon": next((category.icon for category in categories if category.icon), "fa-solid fa-store"),
        "thumbnail_url": business_thumbnail_url(business),
        "phone": business.phone,
        "whatsapp": business.whatsapp,
        "latitude": float(business.latitude) if business.latitude is not None else None,
        "longitude": float(business.longitude) if business.longitude is not None else None,
        "is_open": is_open,
        "open_status": open_status,
        "is_home_delivery": business.is_home_delivery,
        "is_home_collection": business.is_home_collection,
        "distance_km": round(distance_km, 1),
    }


def doctors_near_specialty(specialty, latitude, longitude, page=1):
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(business__geohash__startswith=prefix)

    lat = Cast("business__latitude", FloatField())
    lng = Cast("business__longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )

    queryset = (
        Doctor.objects.filter(
            specialties=specialty,
            is_active=True,
            business__is_testing=False,
            business__is_active=True,
            business__publication_status=Business.PublicationStatus.PUBLISHED,
            business__latitude__isnull=False,
            business__longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("business", "business__locality", "business__locality__city")
        .prefetch_related("specialties")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
    )
    total_count = queryset.count()
    start = (page - 1) * DOCTOR_PAGE_SIZE
    items = list(queryset[start : start + DOCTOR_PAGE_SIZE + 1])
    return items[:DOCTOR_PAGE_SIZE], len(items) > DOCTOR_PAGE_SIZE, total_count


def doctors_nearby_available_today(latitude, longitude, limit=10):
    """Return the nearest active doctors whose next available slot is today."""
    latitude = float(latitude)
    longitude = float(longitude)
    center_hash = pgh.encode(latitude, longitude, precision=5)
    prefixes = neighboring_geohashes(center_hash)
    geohash_filter = Q()
    for prefix in prefixes:
        geohash_filter |= Q(business__geohash__startswith=prefix)

    lat = Cast("business__latitude", FloatField())
    lng = Cast("business__longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    doctors = (
        Doctor.objects.filter(
            is_active=True,
            business__is_testing=False,
            business__is_active=True,
            business__publication_status=Business.PublicationStatus.PUBLISHED,
            business__latitude__isnull=False,
            business__longitude__isnull=False,
        )
        .filter(geohash_filter)
        .select_related("business", "business__locality", "business__locality__city")
        .prefetch_related("specialties")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
    )

    available = []
    for doctor in doctors.iterator(chunk_size=100):
        serialized = serialize_doctor(doctor)
        if serialized["schedule"]["is_today"]:
            available.append(serialized)
            if len(available) == limit:
                break
    return available


def similar_doctors_nearby(doctor, latitude, longitude, limit=10):
    """Return nearby active doctors sharing at least one specialty."""
    specialty_ids = list(doctor.specialties.values_list("id", flat=True))
    if not specialty_ids:
        return []

    latitude = float(latitude)
    longitude = float(longitude)
    lat = Cast("business__latitude", FloatField())
    lng = Cast("business__longitude", FloatField())
    lat_delta = lat - Value(latitude)
    lng_delta = (lng - Value(longitude)) * Value(cos(radians(latitude)))
    distance_degrees = ExpressionWrapper(
        lat_delta * lat_delta + lng_delta * lng_delta,
        output_field=FloatField(),
    )
    doctors = (
        Doctor.objects.filter(
            specialties__id__in=specialty_ids,
            is_active=True,
            business__is_testing=False,
            business__is_active=True,
            business__publication_status=Business.PublicationStatus.PUBLISHED,
            business__latitude__isnull=False,
            business__longitude__isnull=False,
        )
        .exclude(pk=doctor.pk)
        .select_related("business", "business__locality")
        .prefetch_related("specialties")
        .annotate(distance_degrees=distance_degrees)
        .order_by("distance_degrees", "id")
        .distinct()[:limit]
    )
    return [serialize_doctor(item) for item in doctors]


def _schedule_date_matches(rule, day, rule_type):
    if rule_type == "weekly":
        return day.weekday() in rule.get("weekdays", [])
    if rule_type == "monthly_dates":
        return day.day in rule.get("dates", [])
    if rule_type != "monthly_weekday" or day.weekday() not in rule.get("weekdays", []):
        return False
    occurrence = (day.day - 1) // 7 + 1
    is_last = day.day + 7 > calendar.monthrange(day.year, day.month)[1]
    numbers = rule.get("week_numbers", [])
    return occurrence in numbers or (-1 in numbers and is_last)


def _format_schedule_time(value):
    minutes = _parse_time(value)
    return _format_time(minutes) if minutes is not None else value


def _ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def doctor_schedule_availability(schedule, now=None):
    current = timezone.localtime(now or timezone.now(), KOLKATA_TIMEZONE)
    enriched = deepcopy(schedule) if isinstance(schedule, dict) else {}
    schedule_rows = []
    candidates = []
    rule_types = ("weekly", "monthly_weekday", "monthly_dates")

    for rule_type in rule_types:
        rules = enriched.get(rule_type, [])
        if not isinstance(rules, list):
            rules = []
            enriched[rule_type] = rules
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            slots = rule.get("slots", []) if isinstance(rule.get("slots"), list) else []
            formatted_slots = [
                f"{_format_schedule_time(slot.get('start'))} - {_format_schedule_time(slot.get('end'))}"
                for slot in slots
                if isinstance(slot, dict) and _parse_time(slot.get("start")) is not None
                and _parse_time(slot.get("end")) is not None
            ]
            rule["time_text"] = ", ".join(formatted_slots)
            if rule_type == "monthly_dates" and rule.get("dates"):
                dates = ", ".join(_ordinal(date) for date in sorted(rule["dates"]))
                label = f"{dates} of every month"
            else:
                label = rule.get("note") or rule_type.replace("_", " ").title()
            schedule_rows.append(
                {
                    "type": rule_type,
                    "label": label,
                    "time_text": rule["time_text"],
                }
            )

    for offset in range(370):
        day = (current + timedelta(days=offset)).date()
        for rule_type in rule_types:
            for rule in enriched.get(rule_type, []):
                if not isinstance(rule, dict) or not _schedule_date_matches(rule, day, rule_type):
                    continue
                for slot in rule.get("slots", []):
                    if not isinstance(slot, dict):
                        continue
                    start_minutes = _parse_time(slot.get("start"))
                    end_minutes = _parse_time(slot.get("end"))
                    if start_minutes is None or end_minutes is None or start_minutes == end_minutes:
                        continue
                    start = datetime.combine(day, datetime.min.time(), current.tzinfo) + timedelta(minutes=start_minutes)
                    end = datetime.combine(day, datetime.min.time(), current.tzinfo) + timedelta(minutes=end_minutes)
                    if end <= start:
                        end += timedelta(days=1)
                    if end > current:
                        candidates.append((start, end))
        if candidates:
            break

    if candidates:
        start, end = min(candidates, key=lambda item: item[0])
        is_today = start.date() == current.date()
        next_time = f"{_format_time(start.hour * 60 + start.minute)} - {_format_time(end.hour * 60 + end.minute)}"
        next_date = start.strftime("%a, %d %b")
    else:
        is_today = False
        next_time = "Schedule unavailable"
        next_date = ""

    enriched.update(
        {
            "is_today": is_today,
            "next_time": next_time,
            "next_date": next_date,
            "display_rows": schedule_rows,
        }
    )
    return enriched


def serialize_doctor(doctor, now=None):
    distance_km = (doctor.distance_degrees ** 0.5) * 111.195
    business = doctor.business
    return {
        "id": str(doctor.pk),
        "name": doctor.name,
        "slug": doctor.slug,
        "qualification": doctor.qualification,
        "gender": doctor.gender,
        "fees": doctor.fees,
        "bio": doctor.bio,
        "specialties": [specialty.name for specialty in doctor.specialties.all()],
        "business": business.name,
        "business_slug": business.slug,
        "phone": business.phone,
        "locality": business.locality.name if business.locality else "",
        "address": business.address,
        "latitude": float(business.latitude),
        "longitude": float(business.longitude),
        "is_featured": doctor.is_featured,
        "schedule": doctor_schedule_availability(doctor.schedule, now=now),
        "distance_km": round(distance_km, 1),
    }
