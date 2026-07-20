from django.urls import path

from .views import AppointmentLeadCreateView, DoctorDetailView, DoctorListView, DoctorSpecialtyListView


app_name = "doctors"

urlpatterns = [
    path("doctors", DoctorSpecialtyListView.as_view(), name="specialties"),
    path("doctors/<slug:slug>", DoctorListView.as_view(), name="list"),
    path("doctor/<slug:slug>", DoctorDetailView.as_view(), name="detail"),
    path("doctor/<slug:slug>/appointment", AppointmentLeadCreateView.as_view(), name="book-appointment"),
]
