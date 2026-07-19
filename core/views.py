import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from directory.models import Business, Category, Doctor
from directory.services import (
    ambulances_nearby,
    businesses_nearby,
    business_thumbnail_url,
    doctors_nearby_available_today,
    nearby_updates,
)


def _selected_location(request):
    try:
        latitude = float(request.COOKIES["mednearby_location_lat"])
        longitude = float(request.COOKIES["mednearby_location_lng"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return None
    return latitude, longitude


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_specialties"] = Category.objects.filter(
            type=Category.Type.DOCTOR_SPECIALTY,
            is_active=True,
            is_featured=True,
        ).only(
            "name", "label", "slug", "icon", "color", "display_order"
        ).order_by("display_order", "name")
        context["available_doctors"] = []
        context["nearby_businesses"] = []
        context["nearby_updates"] = []
        try:
            latitude = float(self.request.COOKIES["mednearby_location_lat"])
            longitude = float(self.request.COOKIES["mednearby_location_lng"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            pass
        else:
            context["available_doctors"] = doctors_nearby_available_today(
                latitude, longitude, limit=10
            )
            context["nearby_businesses"] = businesses_nearby(
                latitude, longitude, limit=10
            )
            context["nearby_updates"] = nearby_updates(latitude, longitude, limit=10)
        return context


class UpdatesView(TemplateView):
    template_name = "core/updates.html"
    page_size = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = _selected_location(self.request)
        context["location_required"] = location is None
        context["updates"] = []
        context["has_more"] = False
        context["next_page"] = 2
        if location:
            items = list(nearby_updates(*location)[: self.page_size + 1])
            context["updates"] = items[: self.page_size]
            context["has_more"] = len(items) > self.page_size
        return context

    def get(self, request, *args, **kwargs):
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if not is_ajax:
            return super().get(request, *args, **kwargs)

        location = _selected_location(request)
        if location is None:
            return JsonResponse({"error": "A valid selected location is required."}, status=400)
        try:
            page = int(request.GET.get("page", 2))
            if page < 1:
                raise ValueError
        except (TypeError, ValueError):
            return JsonResponse({"error": "A valid page is required."}, status=400)

        start = (page - 1) * self.page_size
        items = list(nearby_updates(*location)[start : start + self.page_size + 1])
        updates = items[: self.page_size]
        return JsonResponse(
            {
                "html": render_to_string(
                    "includes/update_cards.html",
                    {"updates": updates, "updates_horizontal": False},
                    request=request,
                ),
                "has_more": len(items) > self.page_size,
                "next_page": page + 1,
            }
        )


class PrivacyPolicyView(TemplateView):
    template_name = "core/privacy_policy.html"


class TermsOfUseView(TemplateView):
    template_name = "core/terms_of_use.html"


class SupportView(TemplateView):
    template_name = "core/support.html"


class AboutUsView(TemplateView):
    template_name = "core/about_us.html"


class SavedView(TemplateView):
    template_name = "core/saved.html"


class CategoriesView(TemplateView):
    template_name = "core/categories.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_children = Category.objects.filter(is_active=True).order_by(
            "display_order", "name"
        )
        roots = Category.objects.filter(
            is_active=True, parent__isnull=True
        ).order_by("display_order", "name").prefetch_related(
            Prefetch("category_set", queryset=active_children, to_attr="active_children")
        )
        context["business_categories"] = roots.filter(
            type=Category.Type.BUSINESS_CATEGORY
        )
        context["doctor_categories"] = roots.filter(
            type=Category.Type.DOCTOR_SPECIALTY
        )
        return context


class ServiceWorkerView(TemplateView):
    template_name = "core/service-worker.js"
    content_type = "application/javascript"

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["Service-Worker-Allowed"] = "/"
        response["Cache-Control"] = "no-cache"
        return response


class SavedItemsView(View):
    max_items_per_type = 100

    def get(self, request, *args, **kwargs):
        doctor_slugs = list(dict.fromkeys(request.GET.getlist("doctor")))[: self.max_items_per_type]
        business_slugs = list(dict.fromkeys(request.GET.getlist("business")))[: self.max_items_per_type]

        doctors_by_slug = {
            doctor.slug: doctor
            for doctor in Doctor.objects.filter(
                slug__in=doctor_slugs,
                is_active=True,
                business__is_active=True,
                business__is_testing=False,
                business__publication_status=Business.PublicationStatus.PUBLISHED,
            ).prefetch_related(
                Prefetch(
                    "specialties",
                    queryset=Category.objects.order_by("display_order", "name"),
                )
            )
        }
        businesses_by_slug = {
            business.slug: business
            for business in Business.objects.filter(
                slug__in=business_slugs,
                is_active=True,
                is_testing=False,
                publication_status=Business.PublicationStatus.PUBLISHED,
            ).select_related("locality", "locality__city").prefetch_related(
                Prefetch(
                    "categories",
                    queryset=Category.objects.order_by("display_order", "name"),
                )
            )
        }

        doctors = []
        for slug in doctor_slugs:
            doctor = doctors_by_slug.get(slug)
            if doctor:
                doctors.append({
                    "slug": doctor.slug,
                    "name": doctor.name,
                    "url": reverse("doctors:detail", kwargs={"slug": doctor.slug}),
                    "qualification": doctor.qualification,
                    "specialty": ", ".join(item.name for item in doctor.specialties.all()),
                    "fees": doctor.fees or "",
                })

        businesses = []
        for slug in business_slugs:
            business = businesses_by_slug.get(slug)
            if business:
                locality = business.locality
                address = ", ".join(filter(None, [
                    business.address,
                    business.landmark,
                    locality.name if locality else "",
                    locality.city.name if locality and locality.city else "",
                    business.pincode,
                ]))
                businesses.append({
                    "slug": business.slug,
                    "name": business.name,
                    "url": reverse("businesses:detail", kwargs={"slug": business.slug}),
                    "address": address or "Address unavailable",
                    "category": ", ".join(item.name for item in business.categories.all()),
                    "image": business_thumbnail_url(business),
                })

        return JsonResponse({"doctors": doctors, "businesses": businesses})


class EmergencyView(TemplateView):
    template_name = "core/emergency.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = _selected_location(self.request)
        context["location_required"] = location is None
        context["ambulances"] = ambulances_nearby(*location, limit=5) if location else []
        return context


class AmbulanceListView(TemplateView):
    template_name = "core/ambulance_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = _selected_location(self.request)
        context["location_required"] = location is None
        context["ambulances"] = ambulances_nearby(*location) if location else []
        return context


@method_decorator(staff_member_required, name="dispatch")
class InternalTasksView(TemplateView):
    template_name = "core/internal_tasks.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["businesses"] = Business.objects.only(
            "id", "name", "slug"
        ).order_by("name")
        context["doctors"] = Doctor.objects.select_related("business").only(
            "id", "name", "business__name"
        ).order_by("name")
        return context


@method_decorator(staff_member_required, name="dispatch")
class InternalBusinessQRCodeView(View):
    http_method_names = ["get"]

    def get(self, request, business_id, *args, **kwargs):
        import qrcode
        from PIL import Image, ImageDraw

        business = get_object_or_404(Business, pk=business_id)
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
                    (0, 0, badge_size - 1, badge_size - 1), radius=12, fill="white"
                )
                badge.alpha_composite(
                    logo,
                    ((badge_size - logo.width) // 2, (badge_size - logo.height) // 2),
                )
                image.paste(
                    badge.convert("RGB"),
                    ((image.width - badge_size) // 2, (image.height - badge_size) // 2),
                )

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        response = HttpResponse(output.getvalue(), content_type="image/png")
        response["Content-Disposition"] = (
            f'attachment; filename="{business.slug}-mednearby-qr.png"'
        )
        return response


def _valid_time(value):
    try:
        datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        return False
    return True


def _validate_business_hours(value):
    if not isinstance(value, dict):
        return False
    for day, slots in value.items():
        if day not in {str(day_number) for day_number in range(7)} or not isinstance(slots, list):
            return False
        for slot in slots:
            if not isinstance(slot, dict) or not _valid_time(slot.get("opens_at")) or not _valid_time(slot.get("closes_at")):
                return False
    return True


def _normalize_business_services(value):
    if not isinstance(value, list) or len(value) > 100:
        return None
    services = []
    seen = set()
    for service in value:
        if not isinstance(service, str):
            return None
        service = service.strip()
        if not service or len(service) > 100:
            return None
        normalized = service.casefold()
        if normalized not in seen:
            seen.add(normalized)
            services.append(service)
    return services


def _validate_doctor_schedule(value):
    if not isinstance(value, dict):
        return False
    for rule_type in ("weekly", "monthly_weekday", "monthly_dates"):
        rules = value.get(rule_type, [])
        if not isinstance(rules, list):
            return False
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("slots", []), list):
                return False
            for slot in rule.get("slots", []):
                if not isinstance(slot, dict) or not _valid_time(slot.get("start")) or not _valid_time(slot.get("end")):
                    return False
    return True


@method_decorator(staff_member_required, name="dispatch")
class BusinessHoursTaskView(View):
    template_name = "core/business_hours_task.html"

    def get_business(self, business_id):
        return get_object_or_404(Business, pk=business_id)

    def get(self, request, business_id):
        return render(request, self.template_name, {"business": self.get_business(business_id)})

    def post(self, request, business_id):
        business = self.get_business(business_id)
        try:
            hours = json.loads(request.POST.get("business_hours", ""))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid business hours JSON.")
        if not _validate_business_hours(hours):
            return HttpResponseBadRequest("Invalid business hours structure.")
        business.business_hours = hours
        business.save(update_fields=["business_hours"])
        return render(request, self.template_name, {"business": business, "saved": True})


@method_decorator(staff_member_required, name="dispatch")
class BusinessServicesTaskView(View):
    template_name = "core/business_services_task.html"
    common_services = (
        "Blood Test",
        "Blood Pressure Check",
        "Blood Sugar Check",
        "Injection Administration",
        "IV Drip Administration",
        "Dressing and Wound Care",
        "Nebulization",
        "Temperature Check",
        "Oxygen Saturation Check",
        "Suture Removal",
        "Urine Test",
        "Stool Test",
        "Doctor Consultation",
        "Emergency Care",
        "Health Check-up",
        "Diagnostic Tests",
        "X-Ray",
        "Ultrasound",
        "ECG",
        "Home Sample Collection",
        "Home Delivery",
        "Vaccination",
        "Pharmacy",
        "Physiotherapy",
        "Follow-up Care",
        "Ambulance Service",
    )

    def get_business(self, business_id):
        return get_object_or_404(Business, pk=business_id)

    def render_page(self, request, business, saved=False):
        return render(
            request,
            self.template_name,
            {
                "business": business,
                "common_services": self.common_services,
                "saved": saved,
            },
        )

    def get(self, request, business_id):
        return self.render_page(request, self.get_business(business_id))

    def post(self, request, business_id):
        business = self.get_business(business_id)
        try:
            submitted_services = json.loads(request.POST.get("services", ""))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid services JSON.")
        services = _normalize_business_services(submitted_services)
        if services is None:
            return HttpResponseBadRequest("Invalid services structure.")
        business.services = services
        business.save(update_fields=["services"])
        return self.render_page(request, business, saved=True)


@method_decorator(staff_member_required, name="dispatch")
class BusinessTagsTaskView(View):
    template_name = "core/business_tags_task.html"
    common_tags = (
        "Doctors",
        "Pharmacy",
        "Blood Test",
        "Diagnostic Centre",
        "Emergency",
        "X-Ray",
        "Ultrasound",
        "ECG",
        "Follow-up Care",
        "Ambulance Service",
        "Home Sample Collection",
        "Home Delivery",
        "Vaccination",
        "Physiotherapy",
    )

    def get_business(self, business_id):
        return get_object_or_404(Business, pk=business_id)

    def render_page(self, request, business, saved=False):
        return render(request, self.template_name, {
            "business": business,
            "common_tags": self.common_tags,
            "saved": saved,
        })

    def get(self, request, business_id):
        return self.render_page(request, self.get_business(business_id))

    def post(self, request, business_id):
        business = self.get_business(business_id)
        try:
            submitted_tags = json.loads(request.POST.get("tags", ""))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid tags JSON.")
        tags = _normalize_business_services(submitted_tags)
        if tags is None or any("," in tag for tag in tags):
            return HttpResponseBadRequest("Invalid tags structure.")
        stored_tags = ",".join(tags)
        if len(stored_tags) > Business._meta.get_field("tags").max_length:
            return HttpResponseBadRequest("Tags are too long.")
        business.tags = stored_tags
        business.save(update_fields=["tags"])
        return self.render_page(request, business, saved=True)


@method_decorator(staff_member_required, name="dispatch")
class DoctorScheduleTaskView(View):
    template_name = "core/doctor_schedule_task.html"

    def get_doctor(self, doctor_id):
        return get_object_or_404(Doctor.objects.select_related("business"), pk=doctor_id)

    def get(self, request, doctor_id):
        return render(request, self.template_name, {"doctor": self.get_doctor(doctor_id)})

    def post(self, request, doctor_id):
        doctor = self.get_doctor(doctor_id)
        try:
            schedule = json.loads(request.POST.get("schedule", ""))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid doctor schedule JSON.")
        if not _validate_doctor_schedule(schedule):
            return HttpResponseBadRequest("Invalid doctor schedule structure.")
        doctor.schedule = schedule
        doctor.save(update_fields=["schedule"])
        return render(request, self.template_name, {"doctor": doctor, "saved": True})
