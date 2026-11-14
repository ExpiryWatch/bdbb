from __future__ import annotations

import enum
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    and_,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.storage_location import StorageLocation

EXPIRING_SOON_DAYS = 3  # по ТЗ: «Скоро истекает» = осталось от 0 до 3 дней включительно


class ExpiryStatus(str, enum.Enum):
    FRESH = "fresh"                  # Годен
    EXPIRING_SOON = "expiring_soon"  # Скоро истекает
    EXPIRED = "expired"              # Просрочено
    NO_DATE = "no_date"              # Срок не указан


STATUS_LABELS = {
    ExpiryStatus.FRESH: "Годен",
    ExpiryStatus.EXPIRING_SOON: "Скоро истекает",
    ExpiryStatus.EXPIRED: "Просрочено",
    ExpiryStatus.NO_DATE: "Срок не указан",
}


def normalize_text(value: str) -> str:
    """Приведение к виду для поиска и сортировки: без пробелов по краям, нижний регистр, «ё» = «е»."""
    return value.strip().lower().replace("ё", "е")


def calc_days_left(expiry_date: Optional[date], today: Optional[date] = None) -> Optional[int]:
    if expiry_date is None:
        return None
    return (expiry_date - (today or date.today())).days


def calc_status(expiry_date: Optional[date], today: Optional[date] = None) -> ExpiryStatus:
    days = calc_days_left(expiry_date, today)
    if days is None:
        return ExpiryStatus.NO_DATE
    if days < 0:
        return ExpiryStatus.EXPIRED
    if days <= EXPIRING_SOON_DAYS:
        return ExpiryStatus.EXPIRING_SOON
    return ExpiryStatus.FRESH


def _utcnow() -> datetime:
    """Время хранится в UTC без tzinfo (одинаково работает в SQLite и PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StockItem(Base):
    """Позиция домашнего запаса."""

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_items_quantity_positive"),
        CheckConstraint("length(trim(name)) > 0", name="ck_items_name_not_blank"),
        CheckConstraint(
            "expiry_date IS NULL OR purchase_date IS NULL OR expiry_date >= purchase_date",
            name="ck_items_expiry_not_before_purchase",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    # asdecimal=False: в Python приходит обычный float (проще для JSON), в БД хранится NUMERIC(10, 2)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    unit: Mapped[str] = mapped_column(String(16), default="шт", server_default="шт")

    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True, default=None
    )
    storage_location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_locations.id", ondelete="RESTRICT"), index=True, default=None
    )

    purchase_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, index=True, default=None)
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    category: Mapped[Optional["Category"]] = relationship(back_populates="items")
    storage_location: Mapped[Optional["StorageLocation"]] = relationship(back_populates="items")

    @validates("name", "unit", "comment")
    def _clean_text(self, key: str, value):
        """Лишние пробелы по краям убираем; пустой комментарий храним как NULL."""
        if isinstance(value, str):
            value = value.strip()
            if key == "comment" and not value:
                return None
        return value

    # ---- вычисляемые поля (в БД НЕ хранятся, считаются от текущей даты) ----
    @property
    def days_left(self) -> Optional[int]:
        return calc_days_left(self.expiry_date)

    @property
    def status(self) -> ExpiryStatus:
        return calc_status(self.expiry_date)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    # ---- SQL-выражения для фильтрации, поиска и сортировки ----
    @classmethod
    def status_clause(cls, status: ExpiryStatus | str, today: Optional[date] = None):
        """Условие WHERE для фильтра по статусу срока годности (те же правила, что calc_status)."""
        today = today or date.today()
        soon_limit = today + timedelta(days=EXPIRING_SOON_DAYS)
        status = ExpiryStatus(status)
        if status is ExpiryStatus.FRESH:
            return cls.expiry_date > soon_limit
        if status is ExpiryStatus.EXPIRING_SOON:
            return and_(cls.expiry_date >= today, cls.expiry_date <= soon_limit)
        if status is ExpiryStatus.EXPIRED:
            return cls.expiry_date < today
        return cls.expiry_date.is_(None)

    @classmethod
    def name_sort_key(cls):
        """Ключ для сортировки и поиска по названию: нижний регистр и «ё» = «е».

        Без этого SQLite сортирует по кодам символов: «Яблоки» оказались бы раньше «апельсины»
        (заглавные буквы идут перед строчными), а «Мёд» уехал бы после «Молоко».
        """
        return func.replace(func.lower(cls.name), "ё", "е")

    @classmethod
    def search_clause(cls, query: str):
        """Поиск по полному или частичному совпадению названия (регистр и «ё/е» не важны)."""
        escaped = normalize_text(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return cls.name_sort_key().like(f"%{escaped}%", escape="\\")

    def __repr__(self) -> str:
        return f"<StockItem id={self.id} name={self.name!r} qty={self.quantity} {self.unit}>"
