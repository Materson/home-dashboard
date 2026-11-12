
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reminders", "0003_add_reminder_actions"),
    ]

    operations = [
        migrations.AddField(
            model_name="reminder",
            name="link",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
