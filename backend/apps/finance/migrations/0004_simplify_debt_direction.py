"""Collapse the four debt kinds into two directions.

lent + repayment_paid           → gave      (money left the household)
borrowed + repayment_received   → received  (money came in)

The reverse maps back to lent / borrowed; whether an entry was a repayment
is not recoverable, but the balances it produces are identical."""

from django.db import migrations, models

FORWARD = {
    "lent": "gave",
    "repayment_paid": "gave",
    "borrowed": "received",
    "repayment_received": "received",
}
BACKWARD = {"gave": "lent", "received": "borrowed"}


def _remap(mapping):
    def run(apps, _schema_editor):
        DebtEntry = apps.get_model("finance", "DebtEntry")
        for old, new in mapping.items():
            DebtEntry.objects.filter(direction=old).update(direction=new)

    return run


class Migration(migrations.Migration):
    dependencies = [("finance", "0003_add_debt_entry")]

    operations = [
        migrations.RenameField("debtentry", "kind", "direction"),
        migrations.RunPython(_remap(FORWARD), _remap(BACKWARD)),
        migrations.AlterField(
            model_name="debtentry",
            name="direction",
            field=models.CharField(
                choices=[("gave", "We gave them money"), ("received", "They gave us money")],
                max_length=10,
            ),
        ),
    ]
