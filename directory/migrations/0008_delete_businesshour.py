from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("directory", "0007_businesshour_is_24_businesshour_is_closed"),
    ]

    operations = [
        migrations.DeleteModel(name="BusinessHour"),
    ]
