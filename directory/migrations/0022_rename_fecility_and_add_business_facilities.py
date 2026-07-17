from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("directory", "0021_fecility"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Fecility",
            new_name="Facility",
        ),
        migrations.AddField(
            model_name="business",
            name="facilities",
            field=models.ManyToManyField(
                blank=True,
                related_name="businesses",
                to="directory.facility",
            ),
        ),
    ]
