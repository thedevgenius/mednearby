from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from directory.models import Category
from directory.services import businesses_nearby, doctors_nearby_available_today


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
        return context


@method_decorator(staff_member_required, name="dispatch")
class InternalTasksView(TemplateView):
    template_name = "core/internal_tasks.html"
