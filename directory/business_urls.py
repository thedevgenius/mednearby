from django.urls import path

from .views import BusinessDetailView, BusinessListView, BusinessQRCodeView, BusinessLeadActionView, BusinessLeadListView, EnquiryLeadCreateView


app_name = "businesses"

urlpatterns = [
    path("category/<slug:slug>", BusinessListView.as_view(), name="list"),
    path("provider/<slug:slug>", BusinessDetailView.as_view(), name="detail"),
    path("provider/<slug:slug>/qr-code", BusinessQRCodeView.as_view(), name="qr-code"),
    path("provider/<slug:slug>/enquiry", EnquiryLeadCreateView.as_view(), name="send-enquiry"),
    path("account/business/<slug:slug>/leads", BusinessLeadListView.as_view(), name="leads"),
    path("account/business/<slug:slug>/leads/<uuid:lead_id>", BusinessLeadActionView.as_view(), name="lead-action"),
]
