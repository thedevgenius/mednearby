from django.core.exceptions import FieldDoesNotExist
from django.utils.text import slugify


def generate_unique_slug(instance, value, slug_field="slug", fallback="item"):
    """Generate a model-unique slug, adding a numeric counter when needed."""
    try:
        field = instance._meta.get_field(slug_field)
    except FieldDoesNotExist as exc:
        raise ValueError(
            f"{instance.__class__.__name__} has no {slug_field!r} field"
        ) from exc

    max_length = field.max_length
    base_slug = slugify(value) or fallback
    if max_length:
        base_slug = base_slug[:max_length].rstrip("-") or fallback[:max_length]

    model = instance.__class__
    queryset = model._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    candidate = base_slug
    counter = 2
    while queryset.filter(**{slug_field: candidate}).exists():
        suffix = f"-{counter}"
        stem_length = max_length - len(suffix) if max_length else None
        stem = base_slug[:stem_length].rstrip("-") if stem_length is not None else base_slug
        candidate = f"{stem}{suffix}"
        counter += 1

    return candidate
