"""Parents may add, edit and archive family members (People page).

Updates installations whose role groups already exist; fresh installs get it
from ``seed_roles``."""

from django.db import migrations


def grant(apps, _schema_editor):
    Group = apps.get_model("auth", "Group")
    AccessGrant = apps.get_model("access", "AccessGrant")
    parent = Group.objects.filter(name="Parent").first()
    if parent:
        AccessGrant.objects.get_or_create(
            group=parent,
            module="people",
            level="manage",
            effect="allow",
            defaults={"subjects": "all"},
        )


def revoke(apps, _schema_editor):
    AccessGrant = apps.get_model("access", "AccessGrant")
    AccessGrant.objects.filter(group__name="Parent", module="people", level="manage").delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0002_initial"), ("auth", "0012_alter_user_first_name_max_length")]

    operations = [migrations.RunPython(grant, revoke)]
