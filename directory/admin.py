from django.contrib import admin
from django.utils import timezone

from .models import Ambulance, Business, BusinessImage, BusinessUpdate, Category, Doctor, Facility


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "parent",
        "display_order",
        "is_featured",
        "is_active",
    )
    list_display_links = ("name",)
    list_editable = ("display_order", "is_featured", "is_active")
    list_filter = ("type", "is_featured", "is_active")
    search_fields = ("name", "slug", "aliases", "label")
    ordering = ("type", "display_order", "name")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("label",)}
    list_select_related = ("parent",)
    save_on_top = True
    list_per_page = 50

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "type",
                    "name",
                    "label",
                    "slug",
                    "parent",
                    "aliases",
                )
            },
        ),
        ("Presentation", {"fields": ("icon", "color", "display_order")}),
        ("Visibility", {"fields": ("is_featured", "is_active")}),
    )


class BusinessImageInline(admin.TabularInline):
    model = BusinessImage
    extra = 0
    fields = ("image", "is_thumbnail", "created_at")
    readonly_fields = ("created_at",)


class BusinessUpdateInline(admin.StackedInline):
    model = BusinessUpdate
    extra = 0
    fields = ("kind", "title", "summary", "details", "starts_at", "ends_at", "is_published")
    show_change_link = True


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    inlines = (BusinessImageInline, BusinessUpdateInline)
    list_display = (
        "name",
        "locality",
        "verification_status",
        "publication_status",
        "is_active",
        "updated_at",
    )
    list_display_links = ("name",)
    list_editable = ("is_active",)
    list_filter = (
        "verification_status",
        "publication_status",
        "is_active",
        "is_24_7",
        "categories",
    )
    search_fields = (
        "name",
        "slug",
        "address",
        "landmark",
        "pincode",
        "phone",
        "whatsapp",
        "email",
        "locality__name",
        "locality__city__name",
        "categories__name",
    )
    ordering = ("name",)
    autocomplete_fields = ("locality",)
    filter_horizontal = ("categories", "facilities")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = (
        "id",
        "thumbnail_url",
        "geohash",
        "created_at",
        "updated_at",
        "published_at",
    )
    list_select_related = ("locality", "locality__city", "locality__city__state")
    date_hierarchy = "created_at"
    save_on_top = True
    list_per_page = 50
    actions = ("mark_verified", "mark_published", "mark_suspended")

    fieldsets = (
        (
            "Business",
            {
                "fields": (
                    "id",
                    "name",
                    "slug",
                    "categories",
                    "description",
                    "established_year",
                    "thumbnail_url",
                )
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "address",
                    "landmark",
                    "pincode",
                    "locality",
                    "latitude",
                    "longitude",
                    "geohash",
                )
            },
        ),
        ("Contact", {"fields": ("phone", "whatsapp", "email", "website")}),
        ("Availability", {"fields": ("is_active", "is_testing", "is_24_7", "is_emergency", "is_home_collection", "is_home_delivery", "business_hours", "services", "facilities",)}),

        (
            "Moderation",
            {"fields": ("verification_status", "publication_status", "published_at")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.action(description="Mark selected businesses as verified")
    def mark_verified(self, request, queryset):
        queryset.update(verification_status=Business.VerificationStatus.VERIFIED)

    @admin.action(description="Publish selected businesses")
    def mark_published(self, request, queryset):
        queryset.update(
            publication_status=Business.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )

    @admin.action(description="Suspend selected businesses")
    def mark_suspended(self, request, queryset):
        queryset.update(publication_status=Business.PublicationStatus.SUSPENDED)


@admin.register(BusinessUpdate)
class BusinessUpdateAdmin(admin.ModelAdmin):
    list_display = ("title", "business", "kind", "is_published", "starts_at", "ends_at", "created_at")
    list_filter = ("kind", "is_published", "created_at")
    list_editable = ("is_published",)
    search_fields = ("title", "summary", "details", "business__name")
    autocomplete_fields = ("business",)
    list_select_related = ("business",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(Ambulance)
class AmbulanceAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "phone",
        "is_active",
        "is_24_7",
        "updated_at",
    )
    list_display_links = ("business", "phone")
    list_editable = ("is_active", "is_24_7")
    list_filter = ("is_active", "is_24_7", "created_at", "updated_at")
    search_fields = (
        "phone",
        "business__name",
        "business__address",
        "business__locality__name",
    )
    autocomplete_fields = ("business",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("business",)
    ordering = ("business__name", "phone")
    date_hierarchy = "created_at"
    save_on_top = True
    list_per_page = 50

    fieldsets = (
        ("Ambulance", {"fields": ("business", "phone")}),
        ("Availability", {"fields": ("is_active", "is_24_7")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")
    list_display_links = ("name",)
    search_fields = ("name", "icon")
    ordering = ("name",)
    list_per_page = 50

    fieldsets = (
        ("Facility", {"fields": ("name", "icon")}),
    )


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "business",
        "qualification",
        "is_active",
        "is_featured",
        "updated_at",
    )
    list_display_links = ("name",)
    list_editable = ("is_active", "is_featured")
    list_filter = (
        "is_active",
        "is_featured",
        "specialties",
    )
    search_fields = (
        "name",
        "slug",
        "qualification",
        "business__name",
        "specialties__name",
    )
    ordering = ("name",)
    autocomplete_fields = ("business",)
    filter_horizontal = ("specialties",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("business",)
    date_hierarchy = "created_at"
    save_on_top = True
    list_per_page = 50

    fieldsets = (
        ("Doctor", {"fields": ("id", "name", "slug", "business")}),
        ("Professional details", {"fields": ("specialties", "qualification", "gender", "bio")}),
        (
            "Availability",
            {"fields": ("is_active", "is_featured", "fees", "schedule")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
