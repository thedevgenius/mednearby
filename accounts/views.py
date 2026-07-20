from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import ListView

from directory.models import Business

from .forms import PhoneAuthenticationForm


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = PhoneAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("accounts:dashboard")


class AccountLogoutView(LogoutView):
    next_page = "core:home"


class DashboardView(LoginRequiredMixin, ListView):
    template_name = "accounts/dashboard.html"
    context_object_name = "businesses"
    login_url = "accounts:login"

    def get_queryset(self):
        return (
            Business.objects.filter(owner=self.request.user)
            .prefetch_related("categories")
            .order_by("name")
        )

# Create your views here.
