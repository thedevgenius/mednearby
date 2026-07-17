import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from directory.models import Category


IMPORT_FIELDS = {
    "label",
    "slug",
    "type",
    "aliases",
    "icon",
    "color",
    "display_order",
    "is_featured",
    "is_active",
}


class Command(BaseCommand):
    help = "Import categories from a Django fixture JSON file, ignoring fixture PKs."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default="data.json",
            help="Path to the JSON file (default: data.json).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Category data file not found: {path}")

        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CommandError(f"Unable to read category data: {error}") from error
        if not isinstance(records, list):
            raise CommandError("Category data must be a JSON list.")

        fixture_names = {}
        imported_categories = {}
        pending_parents = []
        created = updated = duplicates_deleted = 0

        for index, record in enumerate(records, start=1):
            fields = record.get("fields") if isinstance(record, dict) else None
            if not isinstance(fields, dict) or not fields.get("name"):
                raise CommandError(f"Record {index} must contain fields.name.")

            name = str(fields["name"]).strip()
            if not name:
                raise CommandError(f"Record {index} has an empty category name.")
            fixture_pk = record.get("pk")
            if fixture_pk is not None:
                fixture_names[str(fixture_pk)] = name

            defaults = {field: fields[field] for field in IMPORT_FIELDS if field in fields}
            try:
                matches = list(Category.objects.filter(name__iexact=name).order_by("id"))
                if matches:
                    category = next(
                        (match for match in matches if match.name == name),
                        matches[0],
                    )
                    duplicate_ids = [match.pk for match in matches if match.pk != category.pk]
                    if duplicate_ids:
                        duplicates_deleted += len(duplicate_ids)
                        Category.objects.filter(pk__in=duplicate_ids).delete()
                    was_created = False
                else:
                    category = Category.objects.create(
                        name=name,
                        parent=None,
                    )
                    was_created = True

                incoming_slug = defaults.get("slug")
                if incoming_slug:
                    slug_duplicates = Category.objects.filter(slug=incoming_slug).exclude(
                        pk=category.pk
                    )
                    duplicates_deleted += slug_duplicates.count()
                    slug_duplicates.delete()

                category.name = name
                category.parent = None
                for field, value in defaults.items():
                    setattr(category, field, value)
                category.save()
            except IntegrityError as error:
                raise CommandError(
                    f"Could not import {name!r}; check for conflicting names or slugs."
                ) from error

            created += int(was_created)
            updated += int(not was_created)
            imported_categories[name.casefold()] = category
            pending_parents.append((category, fields.get("parent")))

        for category, parent_fixture_pk in pending_parents:
            if parent_fixture_pk is None:
                continue
            parent_name = fixture_names.get(str(parent_fixture_pk))
            if not parent_name:
                raise CommandError(
                    f"Category {category.name!r} references unknown parent PK {parent_fixture_pk!r}."
                )
            parent = imported_categories.get(parent_name.casefold())
            if parent is None:
                parent = Category.objects.filter(name__iexact=parent_name).first()
            if parent is None:
                raise CommandError(f"Parent category {parent_name!r} was not imported.")
            category.parent = parent
            category.save(update_fields=["parent"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported categories: created {created}, updated {updated}, "
                f"deleted {duplicates_deleted} duplicates."
            )
        )
