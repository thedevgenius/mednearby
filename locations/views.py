from django.http import JsonResponse
from django.views import View

from .services import nearest_locality, search_localities, serialize_locality


class LocalitySearchView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        localities = search_localities(request.GET.get("q", ""))
        return JsonResponse(
            {"results": [serialize_locality(locality) for locality in localities]}
        )


class NearestLocalityView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        try:
            latitude = float(request.GET["lat"])
            longitude = float(request.GET["lng"])
        except (KeyError, TypeError, ValueError):
            return JsonResponse({"error": "Valid lat and lng values are required."}, status=400)

        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return JsonResponse({"error": "Coordinates are outside the valid range."}, status=400)

        locality = nearest_locality(latitude, longitude)
        return JsonResponse(
            {"result": serialize_locality(locality) if locality else None}
        )
