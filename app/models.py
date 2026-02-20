from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model, UserMixin):
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)

    display_name: Mapped[str] = mapped_column(db.String(80), default="User", nullable=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    categories: Mapped[list["Category"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    __table_args__ = (
        CheckConstraint("type IN ('income','expense')", name="ck_category_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(db.String(80), nullable=False)
    type: Mapped[str] = mapped_column(db.String(10), nullable=False)  # income|expense

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", "type", name="uq_category_user_name_type"),
        CheckConstraint("type IN ('income','expense')", name="ck_category_type"),
    )


class Transaction(db.Model):
    __table_args__ = (
        CheckConstraint("type IN ('income','expense')", name="ck_tx_type"),
        CheckConstraint("amount > 0", name="ck_tx_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)

    type: Mapped[str] = mapped_column(db.String(10), nullable=False)  # income|expense
    amount: Mapped[Decimal] = mapped_column(db.Numeric(12, 2), nullable=False)

    tx_date: Mapped[date] = mapped_column(nullable=False, default=date.today)
    note: Mapped[str] = mapped_column(db.String(255), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")