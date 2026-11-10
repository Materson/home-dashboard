"""Debts: the counterparty is plain text for everyone — drop the Person link.

Entries that pointed at a Person get that person's display name, so their
balances carry over unchanged."""

from django.db import migrations, models


def copy_person_names(apps, _schema_editor):
    DebtEntry = apps.get_model("finance", "DebtEntry")
    for entry in DebtEntry.objects.filter(counterparty_person__isnull=False).select_related(
        "counterparty_person"
    ):
        entry.counterparty_name = entry.counterparty_person.display_name
        entry.save(update_fields=["counterparty_name"])


class Migration(migrations.Migration):
    dependencies = [("finance", "0004_simplify_debt_direction")]

    operations = [
        migrations.RemoveConstraint("debtentry", "finance_debt_person_xor_name"),
        # Reverse: names stay filled and the restored link stays empty, which
        # satisfies the old "person xor name" rule — nothing to undo.
        migrations.RunPython(copy_person_names, migrations.RunPython.noop),
        migrations.RemoveField("debtentry", "counterparty_person"),
        migrations.AlterField(
            model_name="debtentry",
            name="counterparty_name",
            field=models.CharField(max_length=120),
        ),
        migrations.AddConstraint(
            model_name="debtentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(counterparty_name=""), name="finance_debt_name_required"
            ),
        ),
    ]
