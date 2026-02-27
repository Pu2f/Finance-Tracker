from collections import defaultdict

from flask import jsonify, redirect, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dash_bp
from ...extensions import db
from ...models import Category, Transaction, TransactionDeletion


@dash_bp.get("/")
@login_required
def dashboard():
    return redirect(url_for("transactions.index"))


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
