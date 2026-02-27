from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import budget_bp
from .forms import BudgetForm
from ...extensions import db
from ...models import Budget, Category, Transaction


def _month_start_from_str(value: str | None) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        return None
    return parsed.replace(day=1)


def _next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _expense_category_choices(user_id: int) -> list[tuple[int, str]]:
    categories = (
        Category.query.filter_by(user_id=user_id, type="expense", is_active=True)
        .order_by(Category.name.asc())
        .all()
    )
    return [(c.id, c.name) for c in categories]


def _build_spent_by_category(user_id: int, month_start: date) -> dict[int, float]:
    month_end = _next_month_start(month_start)
    rows = (
        db.session.query(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("spent"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "expense",
            Transaction.category_id.isnot(None),
            Transaction.tx_date >= month_start,
            Transaction.tx_date < month_end,
        )
        .group_by(Transaction.category_id)
        .all()
    )
    return {int(category_id): float(spent) for category_id, spent in rows if category_id}


@budget_bp.get("/")
@login_required
def index():
    month = request.args.get("month")
    selected_month = _month_start_from_str(month) or date.today().replace(day=1)

    budgets = (
        Budget.query.filter_by(user_id=current_user.id, month_start=selected_month)
        .join(Category, Budget.category_id == Category.id)
        .order_by(Category.name.asc())
        .all()
    )
    spent_by_category = _build_spent_by_category(current_user.id, selected_month)

    budget_rows = []
    for budget in budgets:
        spent = spent_by_category.get(budget.category_id, 0.0)
        budget_amount = float(budget.amount)
        progress = 0.0 if budget_amount == 0 else (spent / budget_amount) * 100
        budget_rows.append(
            {
                "budget": budget,
                "spent": spent,
                "remaining": budget_amount - spent,
                "progress": min(progress, 999.0),
                "is_over": spent > budget_amount,
            }
        )

    return render_template(
        "budgets/index.html",
        month_value=selected_month.strftime("%Y-%m"),
        budget_rows=budget_rows,
    )


@budget_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = BudgetForm()
    form.category_id.choices = _expense_category_choices(current_user.id)

    if not form.category_id.choices:
        flash("ยังไม่มีหมวดหมู่รายจ่ายที่ใช้งานอยู่ โปรดสร้างหมวดหมู่ก่อน", "error")
        return redirect(url_for("categories.create"))

    if request.method == "GET":
        form.month.data = date.today().strftime("%Y-%m")

    if form.validate_on_submit():
        month_start = _month_start_from_str(form.month.data)
        if not month_start:
            flash("รูปแบบเดือนไม่ถูกต้อง", "error")
            return render_template("budgets/form.html", form=form), 400

        category = Category.query.filter_by(
            id=form.category_id.data,
            user_id=current_user.id,
            type="expense",
            is_active=True,
        ).first()
        if not category:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("budgets/form.html", form=form), 400

        budget = Budget(
            user_id=current_user.id,
            category_id=category.id,
            month_start=month_start,
            amount=form.amount.data,
        )
        db.session.add(budget)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("เพิ่มงบไม่สำเร็จ (อาจมีงบหมวดนี้ในเดือนนี้แล้ว)", "error")
            return render_template("budgets/form.html", form=form), 400

        flash("เพิ่มงบประมาณแล้ว", "success")
        return redirect(url_for("budgets.index", month=month_start.strftime("%Y-%m")))

    return render_template("budgets/form.html", form=form)


@budget_bp.route("/<int:budget_id>/edit", methods=["GET", "POST"])
@login_required
def edit(budget_id: int):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    form = BudgetForm(obj=budget)
    form.category_id.choices = _expense_category_choices(current_user.id)

    if request.method == "GET":
        form.month.data = budget.month_start.strftime("%Y-%m")

    if form.validate_on_submit():
        month_start = _month_start_from_str(form.month.data)
        if not month_start:
            flash("รูปแบบเดือนไม่ถูกต้อง", "error")
            return render_template("budgets/form.html", form=form), 400

        category = Category.query.filter_by(
            id=form.category_id.data,
            user_id=current_user.id,
            type="expense",
            is_active=True,
        ).first()
        if not category:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("budgets/form.html", form=form), 400

        budget.category_id = category.id
        budget.month_start = month_start
        budget.amount = form.amount.data
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("แก้ไขงบไม่สำเร็จ (อาจมีงบหมวดนี้ในเดือนนี้แล้ว)", "error")
            return render_template("budgets/form.html", form=form), 400

        flash("แก้ไขงบประมาณแล้ว", "success")
        return redirect(url_for("budgets.index", month=month_start.strftime("%Y-%m")))

    return render_template("budgets/form.html", form=form)


@budget_bp.post("/<int:budget_id>/delete")
@login_required
def delete(budget_id: int):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    month = budget.month_start.strftime("%Y-%m")
    db.session.delete(budget)
    db.session.commit()
    flash("ลบงบประมาณแล้ว", "info")
    return redirect(url_for("budgets.index", month=month))
