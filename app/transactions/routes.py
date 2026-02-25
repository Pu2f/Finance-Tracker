from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import tx_bp
from .forms import TransactionForm
from ..extensions import db
from ..models import Category, Transaction


def _category_choices(user_id: int, tx_type: str):
    cats = (
        Category.query.filter_by(user_id=user_id, type=tx_type, is_active=True)
        .order_by(Category.name.asc())
        .all()
    )
    return [(0, "- ไม่ระบุ -")] + [(c.id, c.name) for c in cats]


@tx_bp.get("/")
@login_required
def index():
    # filters
    tx_type = request.args.get("type")  # income|expense|None
    start = request.args.get("start")
    end = request.args.get("end")

    q = Transaction.query.filter_by(user_id=current_user.id)

    if tx_type in ("income", "expense"):
        q = q.filter(Transaction.type == tx_type)

    def parse_date(s: str | None):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None

    start_d = parse_date(start)
    end_d = parse_date(end)
    if start and start_d is None:
        flash("รูปแบบวันที่เริ่มต้นไม่ถูกต้อง", "error")
    if end and end_d is None:
        flash("รูปแบบวันที่สิ้นสุดไม่ถูกต้อง", "error")
    if start_d:
        q = q.filter(Transaction.tx_date >= start_d)
    if end_d:
        q = q.filter(Transaction.tx_date <= end_d)

    transactions = q.order_by(Transaction.tx_date.desc(), Transaction.id.desc()).limit(200).all()
    return render_template("transactions/index.html", transactions=transactions)


@tx_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = TransactionForm()
    # default type
    if request.method == "GET":
        form.type.data = request.args.get("type", "expense")

    form.category_id.choices = _category_choices(current_user.id, form.type.data or "expense")

    # if type changes on POST, rebuild choices
    if request.method == "POST":
        form.category_id.choices = _category_choices(current_user.id, form.type.data)

    if form.validate_on_submit():
        category_id = form.category_id.data or 0
        selected_category_id = None
        if category_id != 0:
            category = Category.query.filter_by(
                id=category_id,
                user_id=current_user.id,
                type=form.type.data,
                is_active=True,
            ).first()
            if not category:
                flash("หมวดหมู่ไม่ถูกต้อง", "error")
                return render_template("transactions/form.html", form=form), 400
            selected_category_id = category.id

        tx = Transaction(
            user_id=current_user.id,
            type=form.type.data,
            amount=form.amount.data,
            tx_date=form.tx_date.data or date.today(),
            note=(form.note.data or "").strip(),
            category_id=selected_category_id,
        )
        db.session.add(tx)
        db.session.commit()
        flash("เพิ่มรายการแล้ว", "success")
        return redirect(url_for("transactions.index"))

    return render_template("transactions/form.html", form=form)


@tx_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit(tx_id: int):
    tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    form = TransactionForm(obj=tx)

    form.category_id.choices = _category_choices(current_user.id, form.type.data)

    if form.validate_on_submit():
        category_id = form.category_id.data or 0
        selected_category_id = None
        if category_id != 0:
            category = Category.query.filter_by(
                id=category_id,
                user_id=current_user.id,
                type=form.type.data,
                is_active=True,
            ).first()
            if not category:
                flash("หมวดหมู่ไม่ถูกต้อง", "error")
                return render_template("transactions/form.html", form=form), 400
            selected_category_id = category.id

        tx.type = form.type.data
        tx.amount = form.amount.data
        tx.tx_date = form.tx_date.data
        tx.note = (form.note.data or "").strip()
        tx.category_id = selected_category_id
        db.session.commit()
        flash("แก้ไขรายการแล้ว", "success")
        return redirect(url_for("transactions.index"))

    # preload select
    form.category_id.data = tx.category_id or 0
    return render_template("transactions/form.html", form=form)


@tx_bp.post("/<int:tx_id>/delete")
@login_required
def delete(tx_id: int):
    tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    db.session.delete(tx)
    db.session.commit()
    flash("ลบรายการแล้ว", "info")
    return redirect(url_for("transactions.index"))
