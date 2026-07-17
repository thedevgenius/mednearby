from django.urls import path

from .views import (
    AmbulanceListView,
    BusinessHoursTaskView,
    DoctorScheduleTaskView,
    EmergencyView,
    HomeView,
    InternalTasksView,
    PrivacyPolicyView,
    SupportView,
    TermsOfUseView,
)


app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("privacy-policy", PrivacyPolicyView.as_view(), name="privacy-policy"),
    path("terms-of-use", TermsOfUseView.as_view(), name="terms-of-use"),
    path("support", SupportView.as_view(), name="support"),
    path("emergency", EmergencyView.as_view(), name="emergency"),
    path("emergency/ambulances", AmbulanceListView.as_view(), name="ambulances"),
    path("internal/tasks/", InternalTasksView.as_view(), name="internal-tasks"),
    path("internal/tasks/business/<uuid:business_id>/hours/", BusinessHoursTaskView.as_view(), name="business-hours-task"),
    path("internal/tasks/doctor/<uuid:doctor_id>/schedule/", DoctorScheduleTaskView.as_view(), name="doctor-schedule-task"),
]
