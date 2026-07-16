from django.urls import path

from .views import BusinessDetailView, BusinessListView


app_name = "businesses"

urlpatterns = [
    path("category/<slug:slug>", BusinessListView.as_view(), name="list"),
    path("place/<slug:slug>", BusinessDetailView.as_view(), name="detail"),
]
