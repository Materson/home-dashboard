"""Health restructure: visits and treatments hang off an illness/event,
treatments use a cabinet medicine, and medicine purchases live in Finance.

Data conversion (before the purchases table is dropped):
- every treatment is linked to the cabinet medicine with the same name
  (case-insensitive); missing medicines are added to the cabinet;
- every medicine purchase's Finance transaction is kept, detached from the
  purchase row, and linked to its medicine (``related_kind``) — no money
  data is lost.
"""

import django.db.models.deletion
from django.db import migrations, models

CABINET_ITEM_KIND = "health.cabinetitem"


def _item_for(CabinetItem, name, created_by_id):
    name = (name or "").strip()
    if not name:
        return None
    return CabinetItem.objects.filter(name__iexact=name).first() or CabinetItem.objects.create(
        name=name, created_by_id=created_by_id
    )


def convert(apps, _schema_editor):
    CabinetItem = apps.get_model("health", "CabinetItem")
    Medication = apps.get_model("health", "Medication")
    MedicinePurchase = apps.get_model("health", "MedicinePurchase")
    Transaction = apps.get_model("finance", "Transaction")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for med in Medication.objects.filter(cabinet_item__isnull=True):
        med.cabinet_item = _item_for(CabinetItem, med.name, med.created_by_id)
        med.save(update_fields=["cabinet_item"])

    purchase_ct = ContentType.objects.filter(app_label="health", model="medicinepurchase").first()
    for purchase in MedicinePurchase.objects.select_related("medication"):
        name = purchase.medication.name if purchase.medication_id else purchase.name
        item = _item_for(CabinetItem, name, purchase.created_by_id)
        if purchase_ct is None:
            continue
        Transaction.objects.filter(source_type=purchase_ct, source_id=purchase.id).update(
            source_type=None,
            source_id=None,
            related_kind=CABINET_ITEM_KIND if item else "",
            related_id=item.id if item else None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0005_add_appointment_room"),
        ("finance", "0008_add_transaction_related"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="condition",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="appointments",
                to="health.condition",
            ),
        ),
        migrations.AddField(
            model_name="medication",
            name="cabinet_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="treatments",
                to="health.cabinetitem",
            ),
        ),
        # Reverse: the purchase rows can't be rebuilt; links simply stay.
        migrations.RunPython(convert, migrations.RunPython.noop),
        migrations.DeleteModel(name="MedicinePurchase"),
    ]
