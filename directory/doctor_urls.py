from django.urls import path

from .views import DoctorListView, DoctorSpecialtyListView


app_name = "doctors"

urlpatterns = [
    path("doctors", DoctorSpecialtyListView.as_view(), name="specialties"),
    path("doctors/<slug:slug>", DoctorListView.as_view(), name="list"),
]
