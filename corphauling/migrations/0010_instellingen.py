from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corphauling", "0009_haul_date_accepted"),
    ]

    operations = [
        migrations.CreateModel(
            name="Instellingen",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("demo_modus", models.BooleanField(default=False, help_text="Toon voorbeeld-ritten (met DEMO-label) om de weergave te bekijken.")),
            ],
            options={
                "verbose_name": "Corp Hauling instelling",
                "verbose_name_plural": "Corp Hauling instellingen",
                "default_permissions": (),
            },
        ),
    ]
