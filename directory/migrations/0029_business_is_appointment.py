from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("directory", "0028_lead"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="is_appointment",
            field=models.BooleanField(
                default=True,
                help_text="Allow customers to send enquiries and show lead actions.",
            ),
        ),
    ]
