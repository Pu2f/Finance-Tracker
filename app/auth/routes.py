from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from . import auth_bp
from .forms import ChangePasswordForm, LoginForm, ProfileForm, RegisterForm
from ..extensions import db
from ..models import User


@auth_bp.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))
    form = RegisterForm()
    return render_template("auth/register.html", form=form)


@auth_bp.post("/register")
def register_post():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))

    form = RegisterForm()
    if not form.validate_on_submit():
        return render_template("auth/register.html", form=form), 400

    exists = User.query.filter_by(email=form.email.data.lower()).first()
    if exists:
        flash("อีเมลนี้ถูกใช้แล้ว", "error")
        return render_template("auth/register.html", form=form), 400

    user = User(email=form.email.data.lower(), display_name=form.display_name.data.strip())
    user.set_password(form.password.data)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    flash("สมัครสมาชิกสำเร็จ", "success")
    return redirect(url_for("dash.dashboard"))


@auth_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))
    form = LoginForm()
    return render_template("auth/login.html", form=form)


@auth_bp.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))

    form = LoginForm()
    if not form.validate_on_submit():
        return render_template("auth/login.html", form=form), 400

    user = User.query.filter_by(email=form.email.data.lower()).first()
    if not user or not user.check_password(form.password.data):
        flash("อีเมลหรือรหัสผ่านไม่ถูกต้อง", "error")
        return render_template("auth/login.html", form=form), 401

    login_user(user)
    flash("ล็อกอินสำเร็จ", "success")
    next_url = request.args.get("next")
    return redirect(next_url or url_for("dash.dashboard"))


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("ออกจากระบบแล้ว", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.display_name = form.display_name.data.strip()
        db.session.commit()
        flash("อัปเดตโปรไฟล์แล้ว", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("รหัสผ่านเดิมไม่ถูกต้อง", "error")
            return render_template("auth/change_password.html", form=form), 400

        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("เปลี่ยนรหัสผ่านเรียบร้อย", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/change_password.html", form=form)