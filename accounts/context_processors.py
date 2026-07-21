from directory.models import Lead


BOTTOM_NAV_ROUTES = {"home", "categories", "specialties", "saved", "list"}


def dashboard_new_leads(request):
    if not request.user.is_authenticated:
        return {}
    match = getattr(request, "resolver_match", None)
    if not match or match.url_name not in BOTTOM_NAV_ROUTES:
        return {}
    count = Lead.objects.filter(
        business__owner=request.user,
        status=Lead.Status.NEW,
        is_archived=False,
    ).count()
    return {
        "dashboard_new_lead_count": count,
        "dashboard_new_lead_badge": "99+" if count > 99 else str(count),
    }
