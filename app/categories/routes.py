from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from . import cat_bp
from .forms import CategoryForm
from ..extensions import db
from ..models import Category


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
    if form.validate_on_submit():
        cat = Category(
            user_id=current_user.id,
            name=form.name.data.strip(),
            type=form.type.data,
        )
        db.session.add(cat)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("เพิ่มหมวดหมู่ไม่สำเร็จ (อาจชื่อซ้ำ)", "error")
            return render_template("categories/form.html", form=form), 400

        flash("เพิ่มหมวดหมู่แล้ว", "success")
        return redirect(url_for("categories.index"))
    return render_template("categories/form.html", form=form)


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
    if cat.transactions:
        flash("ลบไม่ได้: หมวดนี้มีธุรกรรมอยู่ (แนะนำปิดใช้งานแทน)", "error")
        return redirect(url_for("categories.index"))

    db.session.delete(cat)
    db.session.commit()
    flash("ลบหมวดหมู่แล้ว", "info")
    return redirect(url_for("categories.index"))