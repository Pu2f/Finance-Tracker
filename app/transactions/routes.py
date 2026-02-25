from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import tx_bp
from .forms import TransactionForm
from ..extensions import db
from ..models import Category, Transaction

CATEGORY_OTHER = -1
PRESET_CATEGORY_CHOICES = [
    (-2, "ค่าอาหาร"),
    (-3, "ค่าเดินทาง"),
    (-4, "ค่าที่พัก"),
    (-5, "ค่าน้ำ"),
    (-6, "ค่าไฟ"),
]
PRESET_CATEGORY_NAME_BY_VALUE = {value: name for value, name in PRESET_CATEGORY_CHOICES}


def _category_choices(user_id: int, tx_type: str):
    cats = (
        Category.query.filter_by(user_id=user_id, type=tx_type, is_active=True)
        .order_by(Category.name.asc())
        .all()
    )
    preset_names = set(PRESET_CATEGORY_NAME_BY_VALUE.values())
    dynamic_cats = [c for c in cats if c.name not in preset_names]
    return (
        [(CATEGORY_OTHER, "อื่นๆ (ระบุเอง)")]
        + PRESET_CATEGORY_CHOICES
        + [(c.id, c.name) for c in dynamic_cats]
    )


def _resolve_category_id(form: TransactionForm) -> int | None:
    category_id = form.category_id.data
    typed_name = (form.category_name.data or "").strip()

    if form.type.data == "income":
        if not typed_name:
            return -4
        category = Category.query.filter_by(
            user_id=current_user.id,
            type="income",
            name=typed_name,
        ).first()
        if category:
            if not category.is_active:
                category.is_active = True
            return category.id

        new_category = Category(
            user_id=current_user.id,
            name=typed_name,
            type="income",
            is_active=True,
        )
        db.session.add(new_category)
        db.session.flush()
        return new_category.id

    if category_id == CATEGORY_OTHER:
        if not typed_name:
            return -2
        category = Category.query.filter_by(
            user_id=current_user.id,
            type=form.type.data,
            name=typed_name,
        ).first()
        if category:
            if not category.is_active:
                category.is_active = True
            return category.id

        new_category = Category(
            user_id=current_user.id,
            name=typed_name,
            type=form.type.data,
            is_active=True,
        )
        db.session.add(new_category)
        db.session.flush()
        return new_category.id

    if typed_name:
        return -3

    if category_id in PRESET_CATEGORY_NAME_BY_VALUE:
        preset_name = PRESET_CATEGORY_NAME_BY_VALUE[category_id]
        category = Category.query.filter_by(
            user_id=current_user.id,
            type=form.type.data,
            name=preset_name,
        ).first()
        if category:
            if not category.is_active:
                category.is_active = True
            return category.id

        new_category = Category(
            user_id=current_user.id,
            name=preset_name,
            type=form.type.data,
            is_active=True,
        )
        db.session.add(new_category)
        db.session.flush()
        return new_category.id

    category = Category.query.filter_by(
        id=category_id,
        user_id=current_user.id,
        type=form.type.data,
        is_active=True,
    ).first()
    if not category:
        return -1
    return category.id


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
        selected_category_id = _resolve_category_id(form)
        if selected_category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -2:
            flash("โปรดกรอกชื่อหมวดหมู่เมื่อเลือก 'อื่นๆ'", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -3:
            flash("หากต้องการพิมพ์หมวดหมู่เอง ให้เลือก 'อื่นๆ' ก่อน", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -4:
            flash("โปรดระบุหมวดหมู่รายรับ", "error")
            return render_template("transactions/form.html", form=form), 400

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
        selected_category_id = _resolve_category_id(form)
        if selected_category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -2:
            flash("โปรดกรอกชื่อหมวดหมู่เมื่อเลือก 'อื่นๆ'", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -3:
            flash("หากต้องการพิมพ์หมวดหมู่เอง ให้เลือก 'อื่นๆ' ก่อน", "error")
            return render_template("transactions/form.html", form=form), 400
        if selected_category_id == -4:
            flash("โปรดระบุหมวดหมู่รายรับ", "error")
            return render_template("transactions/form.html", form=form), 400

        tx.type = form.type.data
        tx.amount = form.amount.data
        tx.tx_date = form.tx_date.data
        tx.note = (form.note.data or "").strip()
        tx.category_id = selected_category_id
        db.session.commit()
        flash("แก้ไขรายการแล้ว", "success")
        return redirect(url_for("transactions.index"))

    # preload select/input
    if request.method == "GET" and tx.type == "income" and tx.category:
        form.category_name.data = tx.category.name
        form.category_id.data = CATEGORY_OTHER
    elif tx.category and tx.category.name in PRESET_CATEGORY_NAME_BY_VALUE.values():
        for value, name in PRESET_CATEGORY_CHOICES:
            if name == tx.category.name:
                form.category_id.data = value
                break
    else:
        form.category_id.data = tx.category_id or CATEGORY_OTHER
    return render_template("transactions/form.html", form=form)


@tx_bp.post("/<int:tx_id>/delete")
@login_required
def delete(tx_id: int):
    tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    db.session.delete(tx)
    db.session.commit()
    flash("ลบรายการแล้ว", "info")
    return redirect(url_for("transactions.index"))
