from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


transaction_tag = db.Table(
    "transaction_tag",
    db.Column(
        "transaction_id",
        db.ForeignKey("transaction.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tag_id",
        db.ForeignKey("tag.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.UniqueConstraint("transaction_id", "tag_id", name="uq_transaction_tag_pair"),
)


class User(db.Model, UserMixin):
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        db.String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)

    display_name: Mapped[str] = mapped_column(
        db.String(80), default="User", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    categories: Mapped[list["Category"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recurring_transactions: Mapped[list["RecurringTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    savings_goals: Mapped[list["SavingsGoal"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class TransactionType(enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


TRANSACTION_TYPE_ENUM = Enum(
    TransactionType,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    native_enum=False,
)


class Category(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(db.String(80), nullable=False)
    type: Mapped[TransactionType] = mapped_column(TRANSACTION_TYPE_ENUM, nullable=False)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )
    recurring_transactions: Mapped[list["RecurringTransaction"]] = relationship(
        back_populates="category"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "name", "type", name="uq_category_user_name_type"
        ),
    )


class Transaction(db.Model):
    __table_args__ = (CheckConstraint("amount > 0", name="ck_tx_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[TransactionType] = mapped_column(TRANSACTION_TYPE_ENUM, nullable=False)
    amount: Mapped[Decimal] = mapped_column(db.Numeric(12, 2), nullable=False)

    tx_date: Mapped[date] = mapped_column(nullable=False, default=date.today)
    note: Mapped[str] = mapped_column(db.String(255), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    tags: Mapped[list["Tag"]] = relationship(
        secondary=transaction_tag, back_populates="transactions"
    )


class Tag(db.Model):
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(db.String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="tags")
    transactions: Mapped[list["Transaction"]] = relationship(
        secondary=transaction_tag, back_populates="tags"
    )


class Budget(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "category_id",
            "month_start",
            name="uq_budget_user_category_month",
        ),
        CheckConstraint("amount > 0", name="ck_budget_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month_start: Mapped[date] = mapped_column(nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(db.Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="budgets")
    category: Mapped["Category"] = relationship(back_populates="budgets")


class RecurrenceFrequency(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


RECURRENCE_FREQUENCY_ENUM = Enum(
    RecurrenceFrequency,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    native_enum=False,
)


class RecurringTransaction(db.Model):
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_recurring_amount_positive"),
        CheckConstraint("interval_count > 0", name="ck_recurring_interval_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[TransactionType] = mapped_column(TRANSACTION_TYPE_ENUM, nullable=False)
    amount: Mapped[Decimal] = mapped_column(db.Numeric(12, 2), nullable=False)
    note: Mapped[str] = mapped_column(db.String(255), default="", nullable=False)

    frequency: Mapped[RecurrenceFrequency] = mapped_column(
        RECURRENCE_FREQUENCY_ENUM, nullable=False
    )
    interval_count: Mapped[int] = mapped_column(default=1, nullable=False)

    start_date: Mapped[date] = mapped_column(nullable=False)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    next_run_date: Mapped[date] = mapped_column(nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="recurring_transactions")
    category: Mapped["Category | None"] = relationship(
        back_populates="recurring_transactions"
    )


class SavingsGoal(db.Model):
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_goal_target_positive"),
        CheckConstraint("current_amount >= 0", name="ck_goal_current_non_negative"),
        CheckConstraint(
            "monthly_plan_amount >= 0", name="ck_goal_monthly_plan_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(db.Numeric(12, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        db.Numeric(12, 2), default=0, nullable=False
    )
    monthly_plan_amount: Mapped[Decimal] = mapped_column(
        db.Numeric(12, 2), default=0, nullable=False
    )
    start_date: Mapped[date] = mapped_column(nullable=False, default=date.today)
    target_date: Mapped[date | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="savings_goals")
