from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corphauling", "0008_haul"),
    ]

    operations = [
        migrations.AddField(
            model_name="haul",
            name="date_accepted",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
