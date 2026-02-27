from __future__ import annotations

import calendar
from datetime import date, timedelta

from ..extensions import db
from ..models import RecurrenceFrequency, RecurringTransaction, Transaction


def _add_months(base_date: date, months: int, anchor_day: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor_day, last_day))


def _advance_date(
    run_date: date,
    frequency: RecurrenceFrequency,
    interval_count: int,
    anchor_day: int,
) -> date:
    if frequency == RecurrenceFrequency.DAILY:
        return run_date + timedelta(days=interval_count)
    if frequency == RecurrenceFrequency.WEEKLY:
        return run_date + timedelta(weeks=interval_count)
    return _add_months(run_date, interval_count, anchor_day)


def run_due_recurring_transactions(user_id: int, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    recurring_rows = (
        RecurringTransaction.query.filter(
            RecurringTransaction.user_id == user_id,
            RecurringTransaction.is_active.is_(True),
            RecurringTransaction.next_run_date <= as_of,
        )
        .order_by(RecurringTransaction.next_run_date.asc(), RecurringTransaction.id.asc())
        .all()
    )

    created_count = 0
    for recurring in recurring_rows:
        current_run_date = recurring.next_run_date
        loop_guard = 0

        while current_run_date <= as_of:
            if recurring.end_date and current_run_date > recurring.end_date:
                recurring.is_active = False
                break

            tx = Transaction(
                user_id=recurring.user_id,
                category_id=recurring.category_id,
                type=recurring.type,
                amount=recurring.amount,
                tx_date=current_run_date,
                note=recurring.note,
            )
            db.session.add(tx)
            created_count += 1

            current_run_date = _advance_date(
                current_run_date,
                recurring.frequency,
                recurring.interval_count,
                recurring.start_date.day,
            )
            recurring.next_run_date = current_run_date

            loop_guard += 1
            if loop_guard > 400:
                break

        if recurring.end_date and recurring.next_run_date > recurring.end_date:
            recurring.is_active = False

    if created_count > 0:
        db.session.commit()

    return created_count
