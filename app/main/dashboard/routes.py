from collections import defaultdict, namedtuple
from datetime import date, timedelta
from decimal import Decimal

from flask import jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dash_bp
from ...extensions import db
from ...models import Budget, Category, Transaction, TransactionDeletion, TransactionType


BudgetProgress = namedtuple(
    "BudgetProgress", ["budget", "spent", "progress_pct", "is_over"]
)


def get_budget_progress(user_id: int, month: date) -> list[BudgetProgress]:
    month_start = month.replace(day=1)
    next_month_start = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    budgets = (
        db.session.query(Budget)
        .join(Category)
        .filter(
            Budget.user_id == user_id,
            Budget.month_start == month_start,
            Category.is_active.is_(True),
        )
        .all()
    )

    budget_map = {b.category_id: b for b in budgets}
    if not budget_map:
        return []

    # Get money spent under budgeted categories
    spent_rows = (
        db.session.query(
            Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0)
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.tx_date >= month_start,
            Transaction.tx_date < next_month_start,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.category_id.in_(budget_map.keys()),
        )
        .group_by(Transaction.category_id)
        .all()
    )
    spent_map = {row[0]: row[1] for row in spent_rows}
    results = []
    for category_id, budget in budget_map.items():
        spent = spent_map.get(category_id, Decimal(0))
        is_over = spent > budget.amount
        progress_pct = (spent / budget.amount) * 100 if budget.amount > 0 else 0
        results.append(
            BudgetProgress(
                budget=budget,
                spent=spent,
                is_over=is_over,
                progress_pct=float(progress_pct),
            )
        )
    return results


@dash_bp.get("/")
@login_required
def dashboard():
    # Totals
    income_total_res = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.type == TransactionType.INCOME,
        )
        .scalar()
    )
    expense_total_res = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.type == TransactionType.EXPENSE,
        )
        .scalar()
    )
    balance = income_total_res - expense_total_res

    # Latest transactions
    latest_transactions = (
        db.session.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.tx_date.desc(), Transaction.created_at.desc())
        .limit(5)
        .all()
    )

    # Budget
    today = date.today()
    budget_progress = get_budget_progress(current_user.id, today)

    return render_template(
        "dashboard/index.html",
        income_total=income_total_res,
        expense_total=expense_total_res,
        balance=balance,
        latest_transactions=latest_transactions,
        budget_progress=budget_progress,
        budget_month_label=today.strftime("%B"),
    )



@dash_bp.get("/charts/category-pie")
@login_required
def category_pie():
    tx_type = request.args.get("type", "expense")
    rows = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(Category.user_id == current_user.id, Category.type == tx_type)
        .filter(TransactionDeletion.transaction_id.is_(None))
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    labels = [r[0] for r in rows]
    values = [float(r[1]) for r in rows]
    return jsonify({"labels": labels, "values": values})


@dash_bp.get("/charts/monthly")
@login_required
def monthly():
    # SQLite: group by YYYY-MM
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.tx_date).label("ym"),
            Transaction.type,
            func.coalesce(func.sum(Transaction.amount), 0).label("total"),
        )
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
        )
        .group_by("ym", Transaction.type)
        .order_by("ym")
        .all()
    )

    data = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for ym, ttype, total in rows:
        data[ym][ttype] = float(total)

    labels = sorted(data.keys())
    income = [data[m]["income"] for m in labels]
    expense = [data[m]["expense"] for m in labels]
    return jsonify({"labels": labels, "income": income, "expense": expense})
