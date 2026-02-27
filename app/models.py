from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


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
