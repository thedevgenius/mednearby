import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("directory", "0023_alter_doctor_qualification")]

    operations = [
        migrations.CreateModel(
            name="BusinessUpdate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("announcement", "Announcement"), ("offer", "Offer"), ("doctor_availability", "Doctor availability"), ("new_doctor", "New doctor"), ("other", "Other")], db_index=True, default="announcement", max_length=24)),
                ("title", models.CharField(max_length=160)),
                ("summary", models.CharField(max_length=240)),
                ("details", models.TextField(max_length=3000)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("is_published", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="updates", to="directory.business")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(model_name="businessupdate", index=models.Index(fields=["is_published", "starts_at", "ends_at"], name="update_publish_window_idx")),
        migrations.AddIndex(model_name="businessupdate", index=models.Index(fields=["business", "-created_at"], name="update_business_created_idx")),
    ]
