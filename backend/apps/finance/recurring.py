"""Daily job that materializes due recurring rules into Transactions.

Policy (from the plan)
----------------------
Default: **auto-confirmed**. We create the Transaction for the computed
occurrence and advance ``RecurringRule.next_run_at`` to the next future
occurrence. When the user later edits one of those transactions, the SPA
asks "apply to future occurrences too?" — if yes, ``propagate_edit_to_rule``
rewrites the rule so subsequent runs inherit the new values.

Idempotency
-----------
We advance ``next_run_at`` only after a successful save, and the loop runs
inside a transaction. A duplicate daily run is a no-op because
``next_run_at`` has already moved past today."""

from __future__ import annotations

import logging
from datetime import datetime, time

from dateutil.rrule import rrulestr
from django.db import transaction as db_tx
from django.utils import timezone

from .models import RecurringRule, Transaction

log = logging.getLogger(__name__)


def materialize_due(now: datetime | None = None) -> int:
    """Materialize every active rule whose ``next_run_at`` has arrived.

    Returns the number of transactions created."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    created = 0
    with db_tx.atomic():
        qs = RecurringRule.objects.select_for_update(skip_locked=True).filter(
            is_active=True, next_run_at__lte=today
        )
        for rule in qs:
            created += _advance_rule(rule, today)
    return created


def _advance_rule(rule: RecurringRule, today) -> int:
    """Materialize one rule up to ``today``; advance ``next_run_at``."""
    rule_rrule = rrulestr(
        rule.rrule,
        dtstart=datetime.combine(rule.start_date, time()),
    )
    iter_after = datetime.combine(rule.next_run_at, time()) - _ONE_SECOND
    created = 0
    for occ in rule_rrule.xafter(iter_after, inc=True):
        occ_date = occ.date()
        if rule.end_date and occ_date > rule.end_date:
            rule.is_active = False
            rule.save(update_fields=["is_active", "updated_at"])
            return created
        if occ_date > today:
            rule.next_run_at = occ_date
            rule.save(update_fields=["next_run_at", "updated_at"])
            return created
        Transaction.objects.create(
            date=occ_date,
            amount=rule.amount,
            currency=rule.currency,
            category=rule.category,
            person_id=rule.person_id,
            name=rule.name,
            notes=rule.notes,
            recurring_rule=rule,
        )
        created += 1
    # Rule exhausted (bounded RRULE with COUNT/UNTIL).
    rule.is_active = False
    rule.save(update_fields=["is_active", "updated_at"])
    return created


from datetime import timedelta  # noqa: E402

_ONE_SECOND = timedelta(seconds=1)
