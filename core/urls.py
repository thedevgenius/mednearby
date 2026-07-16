from django.urls import path

from .views import HomeView, InternalTasksView


app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("internal/tasks/", InternalTasksView.as_view(), name="internal-tasks"),
]
