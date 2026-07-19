from django.urls import path

from .views import BusinessDetailView, BusinessListView, BusinessQRCodeView


app_name = "businesses"

urlpatterns = [
    path("category/<slug:slug>", BusinessListView.as_view(), name="list"),
    path("provider/<slug:slug>", BusinessDetailView.as_view(), name="detail"),
    path("provider/<slug:slug>/qr-code", BusinessQRCodeView.as_view(), name="qr-code"),
]
