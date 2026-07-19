from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("directory", "0026_business_tags")]

    operations = [
        migrations.AddField(
            model_name="category",
            name="synonyms",
            field=models.CharField(
                blank=True,
                help_text="Comma-separated familiar names displayed under doctor specialties",
                max_length=500,
            ),
        ),
    ]
