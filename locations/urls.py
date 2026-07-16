from django.urls import path

from .views import LocalitySearchView, NearestLocalityView


app_name = "locations"

urlpatterns = [
    path("search/", LocalitySearchView.as_view(), name="locality-search"),
    path("nearest/", NearestLocalityView.as_view(), name="nearest-locality"),
]
