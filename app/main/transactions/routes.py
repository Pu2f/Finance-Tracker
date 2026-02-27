import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import tx_bp
from .forms import TransactionForm
from ...extensions import db
from ...models import (
    Budget,
    Category,
    SavingsGoal,
    Tag,
    Transaction,
    TransactionDeletion,
)
from ...services.recurring import run_due_recurring_transactions

CATEGORY_OTHER = -1
PRESET_CATEGORY_CHOICES = [
    (-2, "ค่าอาหาร"),
    (-3, "ค่าเดินทาง"),
]
PRESET_CATEGORY_NAME_BY_VALUE = {value: name for value, name in PRESET_CATEGORY_CHOICES}
LEGACY_HIDDEN_EXPENSE_CATEGORIES = {"ค่าที่พัก", "ค่าน้ำ", "ค่าไฟ"}


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _active_transaction_query(user_id: int):
    return (
        Transaction.query.outerjoin(
            TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id
        )
        .filter(
            Transaction.user_id == user_id,
            TransactionDeletion.transaction_id.is_(None),
        )
    )


def _build_filtered_query(user_id: int, tx_type: str | None, start: str | None, end: str | None):
    q = _active_transaction_query(user_id)
    if tx_type in ("income", "expense"):
        q = q.filter(Transaction.type == tx_type)

    start_d = _parse_date(start)
    end_d = _parse_date(end)
    if start_d:
        q = q.filter(Transaction.tx_date >= start_d)
    if end_d:
        q = q.filter(Transaction.tx_date <= end_d)

    return q, start_d, end_d


def _normalize_tag_names(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []
    normalized = []
    seen = set()
    for raw in raw_tags.replace(";", ",").split(","):
        tag = raw.strip().lower()
        if not tag:
            continue
        if len(tag) > 50:
            tag = tag[:50]
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized


def _sync_transaction_tags(tx: Transaction, raw_tags: str | None):
    tag_names = _normalize_tag_names(raw_tags)
    if not tag_names:
        tx.tags = []
        return

    existing_tags = (
        Tag.query.filter(Tag.user_id == tx.user_id, Tag.name.in_(tag_names)).all()
    )
    existing_by_name = {tag.name: tag for tag in existing_tags}

    resolved_tags = []
    for name in tag_names:
        tag = existing_by_name.get(name)
        if tag is None:
            tag = Tag(user_id=tx.user_id, name=name)
            db.session.add(tag)
            db.session.flush()
            existing_by_name[name] = tag
        resolved_tags.append(tag)

    tx.tags = resolved_tags


def _monthly_budget_progress(user_id: int):
    month_start = date.today().replace(day=1)
    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1)

    budgets = (
        Budget.query.filter_by(user_id=user_id, month_start=month_start)
        .join(Category, Budget.category_id == Category.id)
        .order_by(Category.name.asc())
        .all()
    )
    spent_rows = (
        db.session.query(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("spent"),
        )
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == user_id,
            TransactionDeletion.transaction_id.is_(None),
            Transaction.type == "expense",
            Transaction.category_id.isnot(None),
            Transaction.tx_date >= month_start,
            Transaction.tx_date < month_end,
        )
        .group_by(Transaction.category_id)
        .all()
    )
    spent_by_category = {
        int(category_id): float(spent) for category_id, spent in spent_rows if category_id
    }

    budget_progress = []
    for budget in budgets:
        spent = spent_by_category.get(budget.category_id, 0.0)
        amount = float(budget.amount)
        budget_progress.append(
            {
                "budget": budget,
                "spent": spent,
                "remaining": amount - spent,
                "progress_pct": 0.0 if amount == 0 else min((spent / amount) * 100, 999.0),
                "is_over": spent > amount,
            }
        )
    return budget_progress, month_start.strftime("%Y-%m")


def _next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _chart_range_bounds(range_key: str | None):
    today = date.today()
    key = (range_key or "month").strip().lower()
    if key == "day":
        return today, today + timedelta(days=1)
    if key == "week":
        week_start = today - timedelta(days=today.weekday())
        return week_start, week_start + timedelta(days=7)
    if key == "year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    if key == "all":
        return None, None
    # default: current month
    month_start = today.replace(day=1)
    return month_start, _next_month_start(month_start)


def _daily_expense_insight(user_id: int):
    today = date.today()
    current_month_start = today.replace(day=1)
    current_month_end = _next_month_start(current_month_start)
    current_expense = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == user_id,
            TransactionDeletion.transaction_id.is_(None),
            Transaction.type == "expense",
            Transaction.tx_date >= current_month_start,
            Transaction.tx_date < current_month_end,
        )
        .scalar()
    )
    days_elapsed = max(1, (today - current_month_start).days + 1)
    avg_daily_expense = float(current_expense) / days_elapsed

    return {
        "month_label": current_month_start.strftime("%Y-%m"),
        "avg_daily_expense": avg_daily_expense,
        "days_elapsed": days_elapsed,
    }


def _savings_summary(user_id: int):
    goals = (
        SavingsGoal.query.filter_by(user_id=user_id, is_active=True)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    if not goals:
        return {
            "active_count": 0,
            "total_target": 0.0,
            "total_saved": 0.0,
            "progress_pct": 0.0,
            "top_goals": [],
        }

    total_target = sum(float(goal.target_amount) for goal in goals)
    total_saved = sum(float(goal.current_amount) for goal in goals)
    progress_pct = 0.0 if total_target == 0 else min((total_saved / total_target) * 100, 999.0)

    goal_rows = []
    for goal in goals:
        target_amount = float(goal.target_amount)
        saved_amount = float(goal.current_amount)
        row_progress = 0.0 if target_amount == 0 else min((saved_amount / target_amount) * 100, 999.0)
        goal_rows.append(
            {
                "id": goal.id,
                "name": goal.name,
                "saved": saved_amount,
                "target": target_amount,
                "progress_pct": row_progress,
            }
        )
    top_goals = sorted(goal_rows, key=lambda row: row["progress_pct"], reverse=True)[:3]

    return {
        "active_count": len(goals),
        "total_target": total_target,
        "total_saved": total_saved,
        "progress_pct": progress_pct,
        "top_goals": top_goals,
    }


def _category_choices(user_id: int, tx_type: str):
    cats = (
        Category.query.filter_by(user_id=user_id, type=tx_type, is_active=True)
        .order_by(Category.name.asc())
        .all()
    )
    if tx_type == "expense":
        preset_names = set(PRESET_CATEGORY_NAME_BY_VALUE.values())
        dynamic_cats = [
            c
            for c in cats
            if c.name not in preset_names and c.name not in LEGACY_HIDDEN_EXPENSE_CATEGORIES
        ]
        return (
            [(CATEGORY_OTHER, "อื่นๆ (ระบุเอง)")]
            + PRESET_CATEGORY_CHOICES
            + [(c.id, c.name) for c in dynamic_cats]
        )
    return [(CATEGORY_OTHER, "อื่นๆ (ระบุเอง)")] + [(c.id, c.name) for c in cats]


def _category_choices_by_type(user_id: int) -> dict[str, list[tuple[int, str]]]:
    return {
        "income": _category_choices(user_id, "income"),
        "expense": _category_choices(user_id, "expense"),
    }


def _resolve_category_id(form: TransactionForm) -> int | None:
    category_id = form.category_id.data
    typed_name = (form.category_name.data or "").strip()

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
    created_count = run_due_recurring_transactions(current_user.id)
    if created_count > 0:
        flash(f"สร้างรายการอัตโนมัติ {created_count} รายการจาก recurring", "info")

    # filters
    tx_type = request.args.get("type")  # income|expense|None
    start = request.args.get("start")
    end = request.args.get("end")

    q, start_d, end_d = _build_filtered_query(current_user.id, tx_type, start, end)
    if start and start_d is None:
        flash("รูปแบบวันที่เริ่มต้นไม่ถูกต้อง", "error")
    if end and end_d is None:
        flash("รูปแบบวันที่สิ้นสุดไม่ถูกต้อง", "error")

    transactions = q.order_by(Transaction.tx_date.desc(), Transaction.id.desc()).limit(200).all()
    undo_tx_id = request.args.get("undo_tx_id", type=int)
    can_undo_tx_id = None
    if undo_tx_id:
        deletion = TransactionDeletion.query.filter_by(
            transaction_id=undo_tx_id, user_id=current_user.id
        ).first()
        if deletion:
            can_undo_tx_id = undo_tx_id

    income_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
            Transaction.type == "income",
        )
        .scalar()
    )
    expense_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
            Transaction.type == "expense",
        )
        .scalar()
    )
    balance = income_total - expense_total
    budget_progress, budget_month_label = _monthly_budget_progress(current_user.id)
    daily_expense_insight = _daily_expense_insight(current_user.id)
    savings_summary = _savings_summary(current_user.id)

    return render_template(
        "transactions/index.html",
        transactions=transactions,
        income_total=income_total,
        expense_total=expense_total,
        balance=balance,
        budget_progress=budget_progress,
        budget_month_label=budget_month_label,
        daily_expense_insight=daily_expense_insight,
        savings_summary=savings_summary,
        can_undo_tx_id=can_undo_tx_id,
    )


@tx_bp.get("/charts/category-pie")
@login_required
def category_pie():
    tx_type = request.args.get("type", "expense")
    range_start, range_end = _chart_range_bounds(request.args.get("range"))
    rows = (
        db.session.query(Category.name, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.category_id == Category.id)
        .outerjoin(TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id)
        .filter(
            Category.user_id == current_user.id,
            Category.type == tx_type,
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
        )
        .filter(
            Transaction.tx_date >= range_start if range_start else True,
            Transaction.tx_date < range_end if range_end else True,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    labels = [name for name, _ in rows]
    values = [float(total) for _, total in rows]
    return {"labels": labels, "values": values}


@tx_bp.get("/charts/monthly")
@login_required
def monthly():
    range_start, range_end = _chart_range_bounds(request.args.get("range"))
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
            Transaction.tx_date >= range_start if range_start else True,
            Transaction.tx_date < range_end if range_end else True,
        )
        .group_by("ym", Transaction.type)
        .order_by("ym")
        .all()
    )

    data = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for ym, tx_type, total in rows:
        key = tx_type.value if hasattr(tx_type, "value") else str(tx_type)
        data[ym][key] = float(total)

    labels = sorted(data.keys())
    income = [data[m]["income"] for m in labels]
    expense = [data[m]["expense"] for m in labels]
    return {"labels": labels, "income": income, "expense": expense}


@tx_bp.get("/export.csv")
@login_required
def export_csv():
    tx_type = request.args.get("type")
    start = request.args.get("start")
    end = request.args.get("end")

    q, _, _ = _build_filtered_query(current_user.id, tx_type, start, end)
    transactions = q.order_by(Transaction.tx_date.asc(), Transaction.id.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tx_date", "type", "amount", "category", "note", "tags"])
    for tx in transactions:
        writer.writerow(
            [
                tx.tx_date.isoformat(),
                tx.type.value,
                f"{tx.amount:.2f}",
                tx.category.name if tx.category else "",
                tx.note or "",
                ",".join(tag.name for tag in sorted(tx.tags, key=lambda t: t.name)),
            ]
        )

    filename = f"transactions-{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@tx_bp.post("/import.csv")
@login_required
def import_csv():
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("โปรดเลือกไฟล์ CSV", "error")
        return redirect(url_for("transactions.index"))

    try:
        content = file.stream.read().decode("utf-8-sig")
    except Exception:
        flash("อ่านไฟล์ไม่ได้ (ต้องเป็น UTF-8 CSV)", "error")
        return redirect(url_for("transactions.index"))

    reader = csv.DictReader(io.StringIO(content))
    required_cols = {"tx_date", "type", "amount", "category", "note"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        flash("คอลัมน์ CSV ไม่ถูกต้อง: ต้องมี tx_date,type,amount,category,note", "error")
        return redirect(url_for("transactions.index"))

    imported = 0
    skipped = 0
    for row in reader:
        tx_date = _parse_date((row.get("tx_date") or "").strip())
        tx_type = (row.get("type") or "").strip().lower()
        note = (row.get("note") or "").strip()
        category_name = (row.get("category") or "").strip()
        tags_text = (row.get("tags") or "").strip()

        try:
            amount = Decimal((row.get("amount") or "").strip())
        except (InvalidOperation, ValueError):
            skipped += 1
            continue

        if not tx_date or tx_type not in ("income", "expense") or amount <= 0:
            skipped += 1
            continue

        category_id = None
        if category_name:
            category = Category.query.filter_by(
                user_id=current_user.id,
                type=tx_type,
                name=category_name,
            ).first()
            if not category:
                category = Category(
                    user_id=current_user.id,
                    type=tx_type,
                    name=category_name,
                    is_active=True,
                )
                db.session.add(category)
                db.session.flush()
            elif not category.is_active:
                category.is_active = True
            category_id = category.id

        tx = Transaction(
            user_id=current_user.id,
            type=tx_type,
            amount=amount,
            tx_date=tx_date,
            category_id=category_id,
            note=note,
        )
        db.session.add(tx)
        db.session.flush()
        _sync_transaction_tags(tx, tags_text)
        imported += 1

    if imported > 0:
        db.session.commit()
    else:
        db.session.rollback()

    flash(f"นำเข้า CSV สำเร็จ {imported} รายการ, ข้าม {skipped} รายการ", "info")
    return redirect(url_for("transactions.index"))


@tx_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = TransactionForm()
    requested_type = (request.args.get("type") or "").strip().lower()
    if requested_type not in ("income", "expense"):
        requested_type = ""
    # default type
    if request.method == "GET":
        form.type.data = requested_type or "expense"

    form.category_id.choices = _category_choices(current_user.id, form.type.data or "expense")
    category_choices_by_type = _category_choices_by_type(current_user.id)

    # if type changes on POST, rebuild choices
    if request.method == "POST":
        form.category_id.choices = _category_choices(current_user.id, form.type.data)

    if form.validate_on_submit():
        selected_category_id = _resolve_category_id(form)
        if selected_category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type=requested_type,
                ),
                400,
            )
        if selected_category_id == -2:
            flash("โปรดกรอกชื่อหมวดหมู่เมื่อเลือก 'อื่นๆ'", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type=requested_type,
                ),
                400,
            )
        if selected_category_id == -3:
            flash("หากต้องการพิมพ์หมวดหมู่เอง ให้เลือก 'อื่นๆ' ก่อน", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type=requested_type,
                ),
                400,
            )

        tx = Transaction(
            user_id=current_user.id,
            type=form.type.data,
            amount=form.amount.data,
            tx_date=form.tx_date.data or date.today(),
            note=(form.note.data or "").strip(),
            category_id=selected_category_id,
        )
        db.session.add(tx)
        db.session.flush()
        _sync_transaction_tags(tx, form.tags.data)
        db.session.commit()
        flash("เพิ่มรายการแล้ว", "success")
        return redirect(url_for("transactions.index"))

    return render_template(
        "transactions/form.html",
        form=form,
        category_choices_by_type=category_choices_by_type,
        requested_type=requested_type,
    )


@tx_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit(tx_id: int):
    tx = (
        Transaction.query.outerjoin(
            TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id
        )
        .filter(
            Transaction.id == tx_id,
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
        )
        .first_or_404()
    )
    form = TransactionForm(obj=tx)

    form.category_id.choices = _category_choices(current_user.id, form.type.data)
    category_choices_by_type = _category_choices_by_type(current_user.id)

    if form.validate_on_submit():
        selected_category_id = _resolve_category_id(form)
        if selected_category_id == -1:
            flash("หมวดหมู่ไม่ถูกต้อง", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type="",
                ),
                400,
            )
        if selected_category_id == -2:
            flash("โปรดกรอกชื่อหมวดหมู่เมื่อเลือก 'อื่นๆ'", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type="",
                ),
                400,
            )
        if selected_category_id == -3:
            flash("หากต้องการพิมพ์หมวดหมู่เอง ให้เลือก 'อื่นๆ' ก่อน", "error")
            return (
                render_template(
                    "transactions/form.html",
                    form=form,
                    category_choices_by_type=category_choices_by_type,
                    requested_type="",
                ),
                400,
            )

        tx.type = form.type.data
        tx.amount = form.amount.data
        tx.tx_date = form.tx_date.data
        tx.note = (form.note.data or "").strip()
        tx.category_id = selected_category_id
        _sync_transaction_tags(tx, form.tags.data)
        db.session.commit()
        flash("แก้ไขรายการแล้ว", "success")
        return redirect(url_for("transactions.index"))

    # preload select/input
    if request.method == "GET":
        choice_ids = {value for value, _ in form.category_id.choices}
        if tx.category_id in choice_ids:
            form.category_id.data = tx.category_id
        elif tx.category and tx.category.name in PRESET_CATEGORY_NAME_BY_VALUE.values():
            for value, name in PRESET_CATEGORY_CHOICES:
                if name == tx.category.name:
                    form.category_id.data = value
                    break
        else:
            form.category_id.data = CATEGORY_OTHER
            if tx.category:
                form.category_name.data = tx.category.name
    if request.method == "GET":
        form.tags.data = ", ".join(tag.name for tag in sorted(tx.tags, key=lambda t: t.name))
    return render_template(
        "transactions/form.html",
        form=form,
        category_choices_by_type=category_choices_by_type,
        requested_type="",
    )


@tx_bp.post("/<int:tx_id>/delete")
@login_required
def delete(tx_id: int):
    tx = (
        Transaction.query.outerjoin(
            TransactionDeletion, TransactionDeletion.transaction_id == Transaction.id
        )
        .filter(
            Transaction.id == tx_id,
            Transaction.user_id == current_user.id,
            TransactionDeletion.transaction_id.is_(None),
        )
        .first_or_404()
    )
    db.session.add(
        TransactionDeletion(transaction_id=tx.id, user_id=current_user.id)
    )
    db.session.commit()
    flash("ลบรายการแล้ว (กู้คืนได้)", "info")
    return redirect(url_for("transactions.index", undo_tx_id=tx.id))


@tx_bp.post("/<int:tx_id>/undo-delete")
@login_required
def undo_delete(tx_id: int):
    deletion = TransactionDeletion.query.filter_by(
        transaction_id=tx_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(deletion)
    db.session.commit()
    flash("กู้คืนรายการแล้ว", "success")
    return redirect(url_for("transactions.index"))
