from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base

if TYPE_CHECKING:
    from app.models.stock_item import StockItem


class Category(Base):
    """Категория продуктов (например, «Молочные продукты»)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    # passive_deletes="all": ORM не обнуляет category_id у позиций сам,
    # удаление категории с позициями блокирует БД (ON DELETE RESTRICT) -> IntegrityError.
    items: Mapped[list["StockItem"]] = relationship(back_populates="category", passive_deletes="all")

    @validates("name")
    def _strip_name(self, _key: str, value):
        return value.strip() if isinstance(value, str) else value

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"
