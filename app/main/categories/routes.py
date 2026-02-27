from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_

from . import cat_bp
from .forms import CategoryForm
from ...extensions import db
from ...models import Category, Transaction, TransactionDeletion

DEFAULT_INCOME_CATEGORIES = [
    "เงินเดือน",
    "ฟรีแลนซ์/งานเสริม",
    "โบนัส",
    "ดอกเบี้ย/เงินปันผล",
    "รายได้จากการขายของ",
]

DEFAULT_EXPENSE_CATEGORIES = [
    "ค่าอาหาร",
    "ค่าเดินทาง",
    "ค่าเช่า/ค่าที่พัก",
    "ค่าสาธารณูปโภค (น้ำ-ไฟ-เน็ต)",
    "ค่าบันเทิง/ไลฟ์สไตล์",
]


def _add_default_categories_for_user(user_id: int) -> int:
    existing_pairs = {
        (name.strip(), tx_type.value if hasattr(tx_type, "value") else str(tx_type))
        for name, tx_type in db.session.query(Category.name, Category.type)
        .filter(Category.user_id == user_id)
        .all()
    }
    to_create = []
    for name in DEFAULT_INCOME_CATEGORIES:
        if (name, "income") not in existing_pairs:
            to_create.append(Category(user_id=user_id, name=name, type="income"))
    for name in DEFAULT_EXPENSE_CATEGORIES:
        if (name, "expense") not in existing_pairs:
            to_create.append(Category(user_id=user_id, name=name, type="expense"))
    if to_create:
        db.session.add_all(to_create)
    return len(to_create)


@cat_bp.get("/")
@login_required
def index():
    categories = (
        Category.query.filter_by(user_id=current_user.id)
        .order_by(Category.type.asc(), Category.name.asc())
        .all()
    )
    return render_template("categories/index.html", categories=categories)


@cat_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = CategoryForm()
    forced_type = (request.values.get("force_type") or "").strip().lower()
    if forced_type not in ("income", "expense"):
        forced_type = ""

    if request.method == "GET" and forced_type:
        form.type.data = forced_type
    if request.method == "POST" and forced_type:
        form.type.data = forced_type

    if form.validate_on_submit():
        cat = Category(
            user_id=current_user.id,
            name=form.name.data.strip(),
            type=forced_type or form.type.data,
        )
        db.session.add(cat)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("เพิ่มหมวดหมู่ไม่สำเร็จ (อาจชื่อซ้ำ)", "error")
            return render_template("categories/form.html", form=form, forced_type=forced_type), 400

        flash("เพิ่มหมวดหมู่แล้ว", "success")
        return redirect(url_for("categories.index"))
    return render_template("categories/form.html", form=form, forced_type=forced_type)


@cat_bp.route("/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def edit(category_id: int):
    cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first_or_404()
    form = CategoryForm(obj=cat)
    if form.validate_on_submit():
        cat.name = form.name.data.strip()
        cat.type = form.type.data
        db.session.commit()
        flash("แก้ไขหมวดหมู่แล้ว", "success")
        return redirect(url_for("categories.index"))
    return render_template("categories/form.html", form=form)


@cat_bp.post("/<int:category_id>/delete")
@login_required
def delete(category_id: int):
    cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first_or_404()
    has_active_tx = (
        db.session.query(Transaction.id)
        .outerjoin(
            TransactionDeletion,
            and_(
                TransactionDeletion.transaction_id == Transaction.id,
                TransactionDeletion.user_id == current_user.id,
            ),
        )
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.category_id == cat.id,
            TransactionDeletion.transaction_id.is_(None),
        )
        .first()
        is not None
    )
    if has_active_tx:
        flash("ลบไม่ได้: หมวดนี้มีธุรกรรมอยู่ (แนะนำปิดใช้งานแทน)", "error")
        return redirect(url_for("categories.index"))

    db.session.delete(cat)
    db.session.commit()
    flash("ลบหมวดหมู่แล้ว", "info")
    return redirect(url_for("categories.index"))


@cat_bp.post("/seed-defaults")
@login_required
def seed_defaults():
    created_count = _add_default_categories_for_user(current_user.id)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("เพิ่มบางรายการไม่สำเร็จเพราะมีชื่อซ้ำอยู่แล้ว", "info")
        return redirect(url_for("categories.index"))
    if created_count == 0:
        flash("มีหมวดหมู่แนะนำครบแล้ว", "info")
    else:
        flash(f"เพิ่มหมวดหมู่แนะนำแล้ว {created_count} รายการ", "success")
    return redirect(url_for("categories.index"))


@cat_bp.post("/<int:category_id>/toggle-active")
@login_required
def toggle_active(category_id: int):
    cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first_or_404()
    cat.is_active = not cat.is_active
    db.session.commit()
    flash("เปิดใช้งานหมวดหมู่แล้ว" if cat.is_active else "ปิดใช้งานหมวดหมู่แล้ว", "info")
    return redirect(url_for("categories.index"))
