import random
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlencode

from django.http import JsonResponse
from django.http import HttpResponse
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from locations.services import nearest_locality

from .forms import EnquiryLeadForm, LeadForm
from .models import Business, BusinessImage, Category, Doctor, Lead
from .services import (
    KOLKATA_TIMEZONE,
    business_thumbnail_url,
    business_open_status,
    businesses_near_category,
    doctor_schedule_availability,
    doctors_near_specialty,
    published_updates,
    search_categories,
    serialize_business,
    serialize_category,
    serialize_doctor,
    similar_doctors_nearby,
    similar_businesses_nearby,
)


def _format_business_hour(value):
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        return value
    return f"{parsed.hour % 12 or 12}:{parsed.minute:02d} {'AM' if parsed.hour < 12 else 'PM'}"


class AppointmentLeadCreateView(View):
    def post(self, request, slug):
        doctor = get_object_or_404(
            Doctor.objects.select_related("business"),
            slug=slug,
            is_active=True,
            business__is_active=True,
        )
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.business = doctor.business
            lead.doctor = doctor
            lead.lead_type = Lead.LeadType.APPOINTMENT
            lead.status = Lead.Status.NEW
            lead.save()
            return JsonResponse({"ok": True, "message": "Appointment request sent."})
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)


class EnquiryLeadCreateView(View):
    def post(self, request, slug):
        business = get_object_or_404(
            Business,
            slug=slug,
            is_active=True,
            is_appointment=True,
        )
        form = EnquiryLeadForm(request.POST, business=business)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.business = business
            lead.lead_type = Lead.LeadType.ENQUIRY
            lead.status = Lead.Status.NEW
            lead.save()
            return JsonResponse({"ok": True, "message": "Enquiry sent successfully."})
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)


class BusinessLeadListView(LoginRequiredMixin, View):
    login_url = "accounts:login"

    def get_business(self, request, slug):
        return get_object_or_404(Business, slug=slug, owner=request.user)

    def get(self, request, slug):
        business = self.get_business(request, slug)
        leads = (
            business.leads.filter(
                is_archived=False,
                created_at__gte=timezone.now() - timedelta(days=7),
            )
            .select_related("doctor")
            .order_by("-created_at")
        )
        appointment_leads = leads.filter(lead_type=Lead.LeadType.APPOINTMENT)
        enquiry_leads = leads.filter(lead_type=Lead.LeadType.ENQUIRY)
        return render(
            request,
            "accounts/business_leads.html",
            {
                "business": business,
                "has_doctors": business.doctor_set.filter(is_active=True).exists(),
                "appointment_leads": appointment_leads,
                "enquiry_leads": enquiry_leads,
                "new_appointment_count": appointment_leads.filter(status=Lead.Status.NEW).count(),
                "new_enquiry_count": enquiry_leads.filter(status=Lead.Status.NEW).count(),
                "lead_statuses": Lead.Status.choices,
            },
        )


class BusinessLeadActionView(LoginRequiredMixin, View):
    login_url = "accounts:login"

    def post(self, request, slug, lead_id):
        lead = get_object_or_404(Lead, id=lead_id, business__slug=slug, business__owner=request.user)
        if request.POST.get("action") == "delete":
            lead.delete()
            return JsonResponse({"ok": True, "deleted": True})
        if request.POST.get("action") == "toggle-viewed":
            lead.status = (
                Lead.Status.CONTACTED
                if lead.status == Lead.Status.NEW
                else Lead.Status.NEW
            )
            lead.save(update_fields=["status", "updated_at"])
            return JsonResponse({"ok": True, "status": lead.status})
        else:
            valid_statuses = {value for value, _ in Lead.Status.choices}
            status = request.POST.get("status")
            if status not in valid_statuses:
                return JsonResponse({"ok": False, "error": "Invalid status."}, status=400)
            lead.status = status
            lead.save(update_fields=["status", "updated_at"])
        return JsonResponse({"ok": True})


def _distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
    latitude_1, longitude_1, latitude_2, longitude_2 = map(
        radians,
        (latitude_1, longitude_1, latitude_2, longitude_2),
    )
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = longitude_2 - longitude_1
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(longitude_delta / 2) ** 2
    )
    return 6371.0088 * 2 * asin(sqrt(haversine))


class CategorySearchView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        categories = search_categories(request.GET.get("q", ""))
        return JsonResponse(
            {"results": [serialize_category(category) for category in categories]}
        )


class DoctorSpecialtyListView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        specialties = list(
            Category.objects.filter(
                type=Category.Type.DOCTOR_SPECIALTY,
                is_active=True,
                # is_featured=True,
            ).only(
                "name", "label", "slug", "icon", "display_order"
            ).order_by("display_order", "name")
        )
        color_offset = random.SystemRandom().uniform(0, 360)
        color_step = 360 / len(specialties) if specialties else 0
        for index, specialty in enumerate(specialties):
            hue = (color_offset + index * color_step) % 360
            specialty.icon_style = (
                f"background-color: hsl({hue:.2f} 85% 94%); "
                f"color: hsl({hue:.2f} 70% 35%);"
            )
        return render(
            request,
            "directory/doctor_specialty_list.html",
            {"specialties": specialties},
        )


class BusinessListView(View):
    http_method_names = ["get"]

    def get(self, request, slug, *args, **kwargs):
        category = get_object_or_404(
            Category,
            slug=slug,
            type=Category.Type.BUSINESS_CATEGORY,
            is_active=True,
        )
        subcategories = Category.objects.filter(
            parent=category,
            type=Category.Type.BUSINESS_CATEGORY,
            is_active=True,
        ).only("name", "label", "slug", "display_order").order_by(
            "display_order", "name"
        )
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        try:
            latitude = float(request.COOKIES["mednearby_location_lat"])
            longitude = float(request.COOKIES["mednearby_location_lng"])
            page = int(request.GET.get("page", 1))
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or page < 1:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            if is_ajax:
                return JsonResponse(
                    {"error": "A valid selected location is required."},
                    status=400,
                )
            return render(
                request,
                "directory/business_list.html",
                {
                    "category": category,
                    "subcategories": subcategories,
                    "businesses": [],
                    "total_count": 0,
                    "open_now_count": 0,
                    "location_required": True,
                    "canonical_url": request.build_absolute_uri(request.path),
                },
            )

        businesses, has_more, total_count, open_now_count = businesses_near_category(
            category,
            latitude,
            longitude,
            page,
        )
        serialized = [serialize_business(business) for business in businesses]
        if is_ajax:
            return JsonResponse(
                {
                    "results": serialized,
                    "has_more": has_more,
                    "next_page": page + 1,
                    "total_count": total_count,
                    "open_now_count": open_now_count,
                }
            )
        selected_location = nearest_locality(latitude, longitude)
        return render(
            request,
            "directory/business_list.html",
            {
                "category": category,
                "subcategories": subcategories,
                "businesses": serialized,
                "total_count": total_count,
                "open_now_count": open_now_count,
                "has_more": has_more,
                "next_page": page + 1,
                "location_required": False,
                "selected_location": selected_location,
                "canonical_url": request.build_absolute_uri(request.path),
            },
        )


class BusinessDetailView(View):
    http_method_names = ["get"]

    def get(self, request, slug, *args, **kwargs):
        business = get_object_or_404(
            Business.objects.select_related(
                "locality",
                "locality__city",
                "locality__city__state",
            ).prefetch_related(
                Prefetch(
                    "categories",
                    queryset=Category.objects.order_by("display_order", "name"),
                ),
                Prefetch(
                    "images",
                    queryset=BusinessImage.objects.order_by(
                        "-is_thumbnail", "created_at", "id"
                    ),
                    to_attr="detail_images",
                ),
                "facilities",
                Prefetch(
                    "doctor_set",
                    queryset=Doctor.objects.filter(is_active=True).prefetch_related(
                        Prefetch(
                            "specialties",
                            queryset=Category.objects.order_by("display_order", "name"),
                        )
                    ),
                    to_attr="active_doctors",
                ),
            ),
            slug=slug,
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        available_specialties_by_id = {}
        for doctor in business.active_doctors:
            doctor.display_schedule = doctor_schedule_availability(doctor.schedule)
            for specialty in doctor.specialties.all():
                available_specialties_by_id[specialty.pk] = specialty
        available_specialties = sorted(
            available_specialties_by_id.values(),
            key=lambda specialty: (specialty.display_order, specialty.name),
        )
        business_services = (
            [
                service.strip()
                for service in business.services
                if isinstance(service, str) and service.strip()
            ]
            if isinstance(business.services, list)
            else []
        )

        day_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        current_weekday = timezone.localtime(
            timezone.now(),
            KOLKATA_TIMEZONE,
        ).weekday()
        hours = business.business_hours if isinstance(business.business_hours, dict) else {}
        hours_rows = []
        for day_number, day_name in enumerate(day_names):
            slots = hours.get(str(day_number), [])
            slot_labels = []
            if isinstance(slots, list):
                for slot in slots:
                    if isinstance(slot, dict) and slot.get("opens_at") and slot.get("closes_at"):
                        opens_at = _format_business_hour(slot["opens_at"])
                        closes_at = _format_business_hour(slot["closes_at"])
                        slot_labels.append(f"{opens_at} - {closes_at}")
            hours_rows.append(
                {
                    "day": day_name,
                    "hours": "Open 24 Hours" if business.is_24_7 else ", ".join(slot_labels) or "Closed",
                    "is_today": day_number == current_weekday,
                }
            )

        is_open, open_status = business_open_status(
            business.business_hours,
            is_24_7=business.is_24_7,
        )
        years_in_business = None
        if business.established_year:
            years_in_business = max(
                timezone.localdate().year - business.established_year,
                0,
            )
        address_parts = [
            business.address,
            business.landmark,
            business.locality.name if business.locality else "",
            business.locality.city.name if business.locality and business.locality.city else "",
            business.pincode,
        ]
        full_address = ", ".join(part.strip() for part in address_parts if part and part.strip())
        osm_embed_url = ""
        osm_map_url = ""
        google_directions_url = ""
        distance_km = None
        user_latitude = None
        user_longitude = None
        try:
            user_latitude = float(request.COOKIES["mednearby_location_lat"])
            user_longitude = float(request.COOKIES["mednearby_location_lng"])
            if not -90 <= user_latitude <= 90 or not -180 <= user_longitude <= 180:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            user_latitude = None
            user_longitude = None

        if business.latitude is not None and business.longitude is not None:
            latitude = business.latitude
            longitude = business.longitude
            map_offset = Decimal("0.005")
            osm_embed_url = "https://www.openstreetmap.org/export/embed.html?" + urlencode(
                {
                    "bbox": ",".join(
                        str(value)
                        for value in (
                            longitude - map_offset,
                            latitude - map_offset,
                            longitude + map_offset,
                            latitude + map_offset,
                        )
                    ),
                    "layer": "mapnik",
                    "marker": f"{latitude},{longitude}",
                }
            )
            osm_map_url = (
                f"https://www.openstreetmap.org/?mlat={latitude}"
                f"&mlon={longitude}#map=16/{latitude}/{longitude}"
            )
            directions_params = {
                "api": "1",
                "destination": f"{latitude},{longitude}",
            }
            google_directions_url = (
                "https://www.google.com/maps/dir/?" + urlencode(directions_params)
            )
            if user_latitude is not None and user_longitude is not None:
                distance_km = round(
                    _distance_km(
                        user_latitude,
                        user_longitude,
                        float(latitude),
                        float(longitude),
                    ),
                    1,
                )
        similar_businesses = similar_businesses_nearby(business, limit=10)
        business_updates = published_updates().filter(business=business)
        business_url = request.build_absolute_uri(
            reverse("businesses:detail", kwargs={"slug": business.slug})
        )
        thumbnail_url = business_thumbnail_url(business)
        business_thumbnail_absolute_url = request.build_absolute_uri(thumbnail_url)
        seo_categories = ", ".join(
            category.label or category.name for category in business.categories.all()
        )
        seo_location = (
            f"{business.locality.name}, {business.locality.city.name}"
            if business.locality
            else ""
        )
        whatsapp_share_url = "https://api.whatsapp.com/send?" + urlencode(
            {
                "text": (
                    f"Checkout {business.name} on Mednearby - {business_url}. "
                    "Find verified medical services near you and connect with "
                    "them easily!"
                )
            }
        )

        return render(
            request,
            "directory/business_detail.html",
            {
                "business": business,
                "business_thumbnail_url": thumbnail_url,
                "business_thumbnail_absolute_url": business_thumbnail_absolute_url,
                "business_services": business_services,
                "available_specialties": available_specialties,
                "hours_rows": hours_rows,
                "today_hours": hours_rows[current_weekday],
                "has_business_hours": business.is_24_7 or bool(hours),
                "is_open_now": is_open,
                "open_status": open_status,
                "years_in_business": years_in_business,
                "full_address": full_address,
                "osm_embed_url": osm_embed_url,
                "osm_map_url": osm_map_url,
                "google_directions_url": google_directions_url,
                "distance_km": distance_km,
                "similar_businesses": similar_businesses,
                "business_updates": business_updates,
                "whatsapp_share_url": whatsapp_share_url,
                "canonical_url": business_url,
                "seo_categories": seo_categories,
                "seo_location": seo_location,
            },
        )


class BusinessQRCodeView(View):
    http_method_names = ["get"]

    def get(self, request, slug, *args, **kwargs):
        import qrcode
        from PIL import Image, ImageDraw

        business = get_object_or_404(
            Business,
            slug=slug,
            is_testing=False,
            is_active=True,
            publication_status=Business.PublicationStatus.PUBLISHED,
        )
        business_url = request.build_absolute_uri(
            reverse("businesses:detail", kwargs={"slug": business.slug})
        )
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12,
            border=4,
        )
        qr.add_data(business_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#111827", back_color="white").convert("RGB")

        logo_path = Path(settings.BASE_DIR) / "static" / "icons" / "icon-512x512.png"
        if logo_path.exists():
            with Image.open(logo_path) as source_logo:
                logo = source_logo.convert("RGBA")
                logo_size = max(48, image.width // 5)
                logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
                badge_size = max(logo.width, logo.height) + 20
                badge = Image.new("RGBA", (badge_size, badge_size), "white")
                ImageDraw.Draw(badge).rounded_rectangle(
                    (0, 0, badge_size - 1, badge_size - 1),
                    radius=12,
                    fill="white",
                )
                badge.alpha_composite(
                    logo,
                    ((badge_size - logo.width) // 2, (badge_size - logo.height) // 2),
                )
                position = ((image.width - badge_size) // 2, (image.height - badge_size) // 2)
                image.paste(badge.convert("RGB"), position)

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        response = HttpResponse(output.getvalue(), content_type="image/png")
        response["Content-Disposition"] = (
            f'attachment; filename="{business.slug}-mednearby-qr.png"'
        )
        return response


class DoctorListView(View):
    http_method_names = ["get"]

    def get(self, request, slug, *args, **kwargs):
        specialty = get_object_or_404(
            Category,
            slug=slug,
            type=Category.Type.DOCTOR_SPECIALTY,
            is_active=True,
        )
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        try:
            latitude = float(request.COOKIES["mednearby_location_lat"])
            longitude = float(request.COOKIES["mednearby_location_lng"])
            page = int(request.GET.get("page", 1))
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or page < 1:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            if is_ajax:
                return JsonResponse(
                    {"error": "A valid selected location is required."},
                    status=400,
                )
            return render(
                request,
                "directory/doctor_list.html",
                {
                    "specialty": specialty,
                    "doctors": [],
                    "total_count": 0,
                    "available_today_count": 0,
                    "location_required": True,
                    "canonical_url": request.build_absolute_uri(request.path),
                },
            )

        doctors, has_more, total_count, available_today_count = doctors_near_specialty(
            specialty,
            latitude,
            longitude,
            page,
        )
        serialized = [serialize_doctor(doctor) for doctor in doctors]
        if is_ajax:
            return JsonResponse(
                {"results": serialized, "has_more": has_more, "next_page": page + 1, "total_count": total_count, "available_today_count": available_today_count}
            )
        selected_location = nearest_locality(latitude, longitude)
        return render(
            request,
            "directory/doctor_list.html",
            {
                "specialty": specialty,
                "doctors": serialized,
                "total_count": total_count,
                "available_today_count": available_today_count,
                "has_more": has_more,
                "next_page": page + 1,
                "location_required": False,
                "selected_location": selected_location,
                "canonical_url": request.build_absolute_uri(request.path),
            },
        )


class DoctorDetailView(View):
    http_method_names = ["get"]

    def get(self, request, slug, *args, **kwargs):
        doctor = get_object_or_404(
            Doctor.objects.select_related(
                "business",
                "business__locality",
                "business__locality__city",
                "business__locality__city__state",
            ).prefetch_related(
                Prefetch(
                    "specialties",
                    queryset=Category.objects.order_by("display_order", "name"),
                )
            ),
            slug=slug,
            is_active=True,
            business__is_testing=False,
            business__is_active=True,
            business__publication_status=Business.PublicationStatus.PUBLISHED,
        )
        try:
            latitude = float(request.COOKIES["mednearby_location_lat"])
            longitude = float(request.COOKIES["mednearby_location_lng"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            latitude = float(doctor.business.latitude) if doctor.business.latitude is not None else None
            longitude = float(doctor.business.longitude) if doctor.business.longitude is not None else None

        similar_doctors = (
            similar_doctors_nearby(doctor, latitude, longitude)
            if latitude is not None and longitude is not None
            else []
        )
        doctor_url = request.build_absolute_uri(
            reverse("doctors:detail", kwargs={"slug": doctor.slug})
        )
        specialties = list(doctor.specialties.all())
        seo_specialties = ", ".join(
            specialty.label or specialty.name for specialty in specialties
        )
        share_specialization = seo_specialties or "Doctor"
        seo_location = (
            f"{doctor.business.locality.name}, {doctor.business.locality.city.name}"
            if doctor.business.locality
            else ""
        )
        whatsapp_share_url = "https://api.whatsapp.com/send?" + urlencode(
            {
                "text": (
                    f"Found {doctor.name}, {share_specialization} on Mednearby - "
                    f"{doctor_url}. Find verified medical services near you "
                    "and connect with them easily!"
                )
            }
        )
        return render(
            request,
            "directory/doctor_detail.html",
            {
                "doctor": doctor,
                "specialties": specialties,
                "display_schedule": doctor_schedule_availability(doctor.schedule),
                "similar_doctors": similar_doctors,
                "whatsapp_share_url": whatsapp_share_url,
                "canonical_url": doctor_url,
                "seo_specialties": seo_specialties,
                "seo_location": seo_location,
            },
        )
