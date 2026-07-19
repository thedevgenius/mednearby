from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("directory", "0025_business_alternate_phone")]

    operations = [
        migrations.AddField(
            model_name="business",
            name="tags",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
