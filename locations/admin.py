from django.contrib import admin

from .models import City, Locality, State


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "slug")
    search_fields = ("name", "code", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "slug", "pincode_prefixes")
    list_filter = ("state",)
    search_fields = (
        "name",
        "slug",
        "pincode_prefixes",
        "state__name",
        "state__code",
    )
    ordering = ("state__name", "name")
    autocomplete_fields = ("state",)
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("state",)
    list_per_page = 50


@admin.register(Locality)
class LocalityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "city",
        "state_name",
        "locality_type",
        "slug",
        "lattitude",
        "longitude",
    )
    list_filter = ("locality_type", "city__state")
    search_fields = (
        "name",
        "slug",
        "city__name",
        "city__state__name",
        "city__state__code",
    )
    ordering = ("city__state__name", "city__name", "name")
    autocomplete_fields = ("city",)
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("city", "city__state")
    list_per_page = 50

    @admin.display(description="State", ordering="city__state__name")
    def state_name(self, obj):
        return obj.city.state.name
