from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("directory", "0024_businessupdate")]

    operations = [
        migrations.AddField(
            model_name="business",
            name="alternate_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
