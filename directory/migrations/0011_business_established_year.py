from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0010_doctor_fees_doctor_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="established_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
