from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base

if TYPE_CHECKING:
    from app.models.stock_item import StockItem


class StorageLocation(Base):
    """Место хранения (например, «Холодильник», «Кухонный шкаф»)."""

    __tablename__ = "storage_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # В макете у мест хранения своя иконка (снежинка, шкаф). Храним ключ иконки,
    # который фронтенд сопоставляет с картинкой, например "snowflake". Поле необязательное.
    icon: Mapped[Optional[str]] = mapped_column(String(50), default=None)

    items: Mapped[list["StockItem"]] = relationship(back_populates="storage_location", passive_deletes="all")

    @validates("name")
    def _strip_name(self, _key: str, value):
        return value.strip() if isinstance(value, str) else value

    def __repr__(self) -> str:
        return f"<StorageLocation id={self.id} name={self.name!r}>"
