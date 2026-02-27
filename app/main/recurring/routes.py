from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import recurring_bp
from .forms import RecurringTransactionForm
from ...extensions import db
from ...models import Category, RecurringTransaction
from ...services.recurring import run_due_recurring_transactions

NO_CATEGORY = 0


def _category_choices(user_id: int, tx_type: str) -> list[tuple[int, str]]:
    categories = (
        Category.query.filter_by(user_id=user_id, type=tx_type, is_active=True)
        .order_by(Category.name.asc())
        .all()
    )
    return [(NO_CATEGORY, "No category")] + [(c.id, c.name) for c in categories]


def _resolve_category_id(user_id: int, tx_type: str, category_id: int) -> int | None:
    if category_id == NO_CATEGORY:
        return None
    category = Category.query.filter_by(
        id=category_id,
        user_id=user_id,
        type=tx_type,
        is_active=True,
    ).first()
    if not category:
        return -1
    return category.id


@recurring_bp.get("/")
@login_required
def index():
    created_count = run_due_recurring_transactions(current_user.id)
    if created_count > 0:
        flash(f"สร้างรายการอัตโนมัติ {created_count} รายการจาก recurring", "info")

    rows = (
        RecurringTransaction.query.filter_by(user_id=current_user.id)
        .order_by(RecurringTransaction.created_at.desc())
        .all()
    )
    return render_template("recurring/index.html", recurring_rows=rows)


@recurring_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = RecurringTransactionForm()
    if request.method == "GET":
        form.type.data = request.args.get("type", "expense")
        form.interval_count.data = 1
        form.is_active.data = True

    form.category_id.choices = _category_choices(current_user.id, form.type.data or "expense")

    if request.method == "POST":
        form.category_id.choices = _category_choices(current_user.id, form.type.data)

    if form.validate_on_submit():
        category_id = _resolve_category_id(current_user.id, form.type.data, form.category_id.data)
        if category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("recurring/form.html", form=form), 400

        recurring = RecurringTransaction(
            user_id=current_user.id,
            category_id=category_id,
            type=form.type.data,
            amount=form.amount.data,
            note=(form.note.data or "").strip(),
            frequency=form.frequency.data,
            interval_count=form.interval_count.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            next_run_date=form.start_date.data,
            is_active=bool(form.is_active.data),
        )
        db.session.add(recurring)
        db.session.commit()
        flash("เพิ่ม recurring transaction แล้ว", "success")
        return redirect(url_for("recurring.index"))

    return render_template("recurring/form.html", form=form)


@recurring_bp.route("/<int:recurring_id>/edit", methods=["GET", "POST"])
@login_required
def edit(recurring_id: int):
    recurring = RecurringTransaction.query.filter_by(
        id=recurring_id, user_id=current_user.id
    ).first_or_404()

    form = RecurringTransactionForm(obj=recurring)
    if request.method == "GET":
        form.type.data = recurring.type.value
        form.frequency.data = recurring.frequency.value
        form.category_id.data = recurring.category_id or NO_CATEGORY
    form.category_id.choices = _category_choices(
        current_user.id, form.type.data or recurring.type.value
    )

    if request.method == "POST":
        form.category_id.choices = _category_choices(current_user.id, form.type.data)

    if form.validate_on_submit():
        category_id = _resolve_category_id(current_user.id, form.type.data, form.category_id.data)
        if category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("recurring/form.html", form=form), 400

        recurring.type = form.type.data
        recurring.amount = form.amount.data
        recurring.frequency = form.frequency.data
        recurring.interval_count = form.interval_count.data
        recurring.start_date = form.start_date.data
        recurring.end_date = form.end_date.data
        recurring.note = (form.note.data or "").strip()
        recurring.category_id = category_id
        recurring.is_active = bool(form.is_active.data)

        if recurring.next_run_date < recurring.start_date:
            recurring.next_run_date = recurring.start_date

        db.session.commit()
        flash("แก้ไข recurring transaction แล้ว", "success")
        return redirect(url_for("recurring.index"))

    return render_template("recurring/form.html", form=form)


@recurring_bp.post("/<int:recurring_id>/toggle")
@login_required
def toggle(recurring_id: int):
    recurring = RecurringTransaction.query.filter_by(
        id=recurring_id, user_id=current_user.id
    ).first_or_404()
    recurring.is_active = not recurring.is_active
    db.session.commit()
    flash("อัปเดตสถานะ recurring แล้ว", "info")
    return redirect(url_for("recurring.index"))


@recurring_bp.post("/<int:recurring_id>/delete")
@login_required
def delete(recurring_id: int):
    recurring = RecurringTransaction.query.filter_by(
        id=recurring_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(recurring)
    db.session.commit()
    flash("ลบ recurring transaction แล้ว", "info")
    return redirect(url_for("recurring.index"))
