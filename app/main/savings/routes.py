import calendar
from datetime import date
from decimal import Decimal

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from . import savings_bp
from .forms import SavingsContributionForm, SavingsGoalForm
from ...extensions import db
from ...models import SavingsGoal


def _add_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _goal_view(goal: SavingsGoal):
    target_amount = float(goal.target_amount)
    current_amount = float(goal.current_amount)
    progress_pct = 0.0 if target_amount == 0 else min((current_amount / target_amount) * 100, 999.0)
    remaining = max(0.0, target_amount - current_amount)
    is_completed = current_amount >= target_amount

    estimated_date = None
    if not is_completed and float(goal.monthly_plan_amount) > 0:
        months_needed = int(-(-remaining // float(goal.monthly_plan_amount)))
        estimated_date = _add_months(date.today(), months_needed)

    return {
        "goal": goal,
        "progress_pct": progress_pct,
        "remaining": remaining,
        "is_completed": is_completed,
        "estimated_date": estimated_date,
    }


@savings_bp.get("/")
@login_required
def index():
    goals = (
        SavingsGoal.query.filter_by(user_id=current_user.id)
        .order_by(SavingsGoal.is_active.desc(), SavingsGoal.created_at.desc())
        .all()
    )
    goal_views = [_goal_view(goal) for goal in goals]
    return render_template("savings/index.html", goal_views=goal_views)


@savings_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = SavingsGoalForm()
    if form.validate_on_submit():
        goal = SavingsGoal(
            user_id=current_user.id,
            name=form.name.data.strip(),
            target_amount=form.target_amount.data,
            current_amount=form.current_amount.data,
            monthly_plan_amount=form.monthly_plan_amount.data,
            start_date=form.start_date.data,
            target_date=form.target_date.data,
            is_active=bool(form.is_active.data),
        )
        db.session.add(goal)
        db.session.commit()
        flash("เพิ่มเป้าหมายการออมแล้ว", "success")
        return redirect(url_for("savings.index"))

    return render_template("savings/form.html", form=form)


@savings_bp.route("/<int:goal_id>/edit", methods=["GET", "POST"])
@login_required
def edit(goal_id: int):
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    form = SavingsGoalForm(obj=goal)

    if form.validate_on_submit():
        goal.name = form.name.data.strip()
        goal.target_amount = form.target_amount.data
        goal.current_amount = form.current_amount.data
        goal.monthly_plan_amount = form.monthly_plan_amount.data
        goal.start_date = form.start_date.data
        goal.target_date = form.target_date.data
        goal.is_active = bool(form.is_active.data)
        db.session.commit()
        flash("แก้ไขเป้าหมายการออมแล้ว", "success")
        return redirect(url_for("savings.index"))

    return render_template("savings/form.html", form=form)


@savings_bp.route("/<int:goal_id>/contribute", methods=["GET", "POST"])
@login_required
def contribute(goal_id: int):
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    form = SavingsContributionForm()
    if form.validate_on_submit():
        goal.current_amount = Decimal(goal.current_amount) + form.amount.data
        db.session.commit()
        flash("บันทึกเงินออมเข้าเป้าหมายแล้ว", "success")
        return redirect(url_for("savings.index"))

    return render_template("savings/contribute.html", form=form, goal=goal)


@savings_bp.post("/<int:goal_id>/toggle")
@login_required
def toggle(goal_id: int):
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    goal.is_active = not goal.is_active
    db.session.commit()
    flash("อัปเดตสถานะเป้าหมายแล้ว", "info")
    return redirect(url_for("savings.index"))


@savings_bp.post("/<int:goal_id>/delete")
@login_required
def delete(goal_id: int):
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    db.session.delete(goal)
    db.session.commit()
    flash("ลบเป้าหมายการออมแล้ว", "info")
    return redirect(url_for("savings.index"))
