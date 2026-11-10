
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0008_track_symptoms_over_time"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="symptom",
            name="severity",
        ),
    ]
