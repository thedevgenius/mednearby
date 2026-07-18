from django.urls import path

from .views import (
    AboutUsView,
    AmbulanceListView,
    BusinessHoursTaskView,
    CategoriesView,
    DoctorScheduleTaskView,
    EmergencyView,
    HomeView,
    InternalTasksView,
    InternalBusinessQRCodeView,
    PrivacyPolicyView,
    SavedView,
    SavedItemsView,
    ServiceWorkerView,
    SupportView,
    TermsOfUseView,
    UpdatesView,
)


app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("privacy-policy", PrivacyPolicyView.as_view(), name="privacy-policy"),
    path("terms-of-use", TermsOfUseView.as_view(), name="terms-of-use"),
    path("support", SupportView.as_view(), name="support"),
    path("about", AboutUsView.as_view(), name="about-us"),
    path("saved", SavedView.as_view(), name="saved"),
    path("saved/items", SavedItemsView.as_view(), name="saved-items"),
    path("categories", CategoriesView.as_view(), name="categories"),
    path("service-worker.js", ServiceWorkerView.as_view(), name="service-worker"),
    path("updates", UpdatesView.as_view(), name="updates"),
    path("emergency", EmergencyView.as_view(), name="emergency"),
    path("emergency/ambulances", AmbulanceListView.as_view(), name="ambulances"),
    path("internal/tasks/", InternalTasksView.as_view(), name="internal-tasks"),
    path("internal/tasks/business/<uuid:business_id>/qr-code/", InternalBusinessQRCodeView.as_view(), name="internal-business-qr-code"),
    path("internal/tasks/business/<uuid:business_id>/hours/", BusinessHoursTaskView.as_view(), name="business-hours-task"),
    path("internal/tasks/doctor/<uuid:doctor_id>/schedule/", DoctorScheduleTaskView.as_view(), name="doctor-schedule-task"),
]
