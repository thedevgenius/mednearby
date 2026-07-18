import json
from datetime import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from directory.models import Business, Category, Doctor
from directory.services import (
    ambulances_nearby,
    businesses_nearby,
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
        ).only("name", "label", "slug", "icon", "color", "display_order")
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
        context["businesses"] = Business.objects.only("id", "name").order_by("name")
        context["doctors"] = Doctor.objects.select_related("business").only(
            "id", "name", "business__name"
        ).order_by("name")
        return context


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
