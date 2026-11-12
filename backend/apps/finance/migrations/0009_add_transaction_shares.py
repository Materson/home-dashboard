"""Who a transaction was for, split between people: TransactionShare, plus
the same split on recurring rules and bookmarks. Existing "for whom"
persons become a single full-amount share (the reverse puts them back)."""

import django.db.models.deletion
from django.db import migrations, models


def person_to_shares(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")
    TransactionShare = apps.get_model("finance", "TransactionShare")
    TransactionShare.objects.bulk_create(
        TransactionShare(transaction_id=tx.id, person_id=tx.person_id, amount=tx.amount)
        for tx in Transaction.objects.exclude(person_id=None).only("id", "person_id", "amount")
    )
    for name in ("RecurringRule", "TransactionBookmark"):
        model = apps.get_model("finance", name)
        for row in model.objects.exclude(person_id=None):
            row.shares = [{"person_id": str(row.person_id), "amount": f"{row.amount:.2f}"}]
            row.save(update_fields=["shares"])


def shares_to_person(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")
    TransactionShare = apps.get_model("finance", "TransactionShare")
    for tx in Transaction.objects.filter(person_id=None):
        shares = list(TransactionShare.objects.filter(transaction_id=tx.id))
        if len(shares) == 1:
            tx.person_id = shares[0].person_id
            tx.save(update_fields=["person"])
    for name in ("RecurringRule", "TransactionBookmark"):
        model = apps.get_model("finance", name)
        for row in model.objects.filter(person_id=None):
            if len(row.shares) == 1:
                row.person_id = row.shares[0]["person_id"]
                row.save(update_fields=["person"])



class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_add_transaction_related"),
        ("people", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="recurringrule",
            name="shares",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="transactionbookmark",
            name="shares",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="TransactionShare",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="people.person",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="finance.transaction",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("transaction", "person"), name="finance_share_once"
                    )
                ],
            },
        ),
        migrations.RunPython(person_to_shares, shares_to_person),
    ]
