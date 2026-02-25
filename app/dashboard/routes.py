from collections import defaultdict
from datetime import date

from flask import jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dash_bp
from ..extensions import db
from ..models import Category, Transaction


@dash_bp.get("/")
@login_required
def dashboard():
    income_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "income")
        .scalar()
    )
    expense_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.user_id == current_user.id, Transaction.type == "expense")
        .scalar()
    )
    balance = income_total - expense_total
    latest_transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.tx_date.desc(), Transaction.id.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard/index.html",
        income_total=income_total,
        expense_total=expense_total,
        balance=balance,
        latest_transactions=latest_transactions,
    )


@dash_bp.get("/charts/category-pie")
@login_required
def category_pie():
    tx_type = request.args.get("type", "expense")
    rows = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Category.user_id == current_user.id, Category.type == tx_type)
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
        .filter(Transaction.user_id == current_user.id)
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
