
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("household", "0001_create_household"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="item",
            name="location",
        ),
    ]
