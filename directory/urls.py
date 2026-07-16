from django.urls import path

from .views import CategorySearchView


app_name = "directory"

urlpatterns = [
    path("categories/", CategorySearchView.as_view(), name="category-search"),
]
