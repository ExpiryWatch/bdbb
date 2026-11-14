"""Готовые запросы для backend (FastAPI-роуты просто вызывают эти функции).

Все функции только читают данные. Создание, изменение и удаление делаются через ORM
(`db.add`, изменение полей, `db.delete`, затем `db.commit()`).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Category, ExpiryStatus, StockItem, StorageLocation

SortField = Literal["name", "expiry"]
SortOrder = Literal["asc", "desc"]


def _apply_filters(stmt, *, q, category_id, storage_location_id, status, today):
    if q and q.strip():
        stmt = stmt.where(StockItem.search_clause(q))
    if category_id is not None:
        stmt = stmt.where(StockItem.category_id == category_id)
    if storage_location_id is not None:
        stmt = stmt.where(StockItem.storage_location_id == storage_location_id)
    if status is not None:
        stmt = stmt.where(StockItem.status_clause(status, today))
    return stmt


def _order_by(sort: str, order: str):
    if sort not in ("name", "expiry"):
        raise ValueError(f"Неизвестное поле сортировки: {sort!r} (допустимо: 'name', 'expiry')")
    if order not in ("asc", "desc"):
        raise ValueError(f"Неизвестное направление сортировки: {order!r} (допустимо: 'asc', 'desc')")
    name_key = StockItem.name_sort_key()
    direction = (lambda col: col.desc()) if order == "desc" else (lambda col: col.asc())
    if sort == "expiry":
        return (
            StockItem.expiry_date.is_(None),   # позиции без срока всегда в конце (и по возрастанию, и по убыванию)
            direction(StockItem.expiry_date),
            name_key.asc(),                    # при равных датах порядок по названию
            StockItem.id,
        )
    return (direction(name_key), StockItem.id)  # id добавлен, чтобы порядок был стабильным


def list_items(
    db: Session,
    *,
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    storage_location_id: Optional[int] = None,
    status: Optional[ExpiryStatus | str] = None,
    sort: SortField = "name",
    order: SortOrder = "asc",
    limit: Optional[int] = None,
    offset: int = 0,
    today: Optional[date] = None,
) -> list[StockItem]:
    """Главный запрос списка: поиск + фильтры + сортировка (+ постраничность)."""
    stmt = select(StockItem).options(joinedload(StockItem.category), joinedload(StockItem.storage_location))
    stmt = _apply_filters(
        stmt, q=q, category_id=category_id, storage_location_id=storage_location_id, status=status, today=today
    )
    stmt = stmt.order_by(*_order_by(sort, order))
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt))


def count_items(
    db: Session,
    *,
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    storage_location_id: Optional[int] = None,
    status: Optional[ExpiryStatus | str] = None,
    today: Optional[date] = None,
) -> int:
    """Сколько позиций подходит под условия (для надписи «6 из 6» в списке)."""
    stmt = select(func.count(StockItem.id))
    stmt = _apply_filters(
        stmt, q=q, category_id=category_id, storage_location_id=storage_location_id, status=status, today=today
    )
    return db.scalar(stmt) or 0


# ---- запросы по категории и месту хранения ----
def get_items_by_category(db: Session, category_id: int, **kwargs) -> list[StockItem]:
    return list_items(db, category_id=category_id, **kwargs)


def get_items_by_storage_location(db: Session, storage_location_id: int, **kwargs) -> list[StockItem]:
    return list_items(db, storage_location_id=storage_location_id, **kwargs)


def get_items_by_category_and_location(
    db: Session, category_id: int, storage_location_id: int, **kwargs
) -> list[StockItem]:
    return list_items(db, category_id=category_id, storage_location_id=storage_location_id, **kwargs)


# ---- справочники ----
def list_categories_with_counts(db: Session) -> list[tuple[Category, int]]:
    """Категории и количество позиций в каждой (пустые категории тоже возвращаются, с нулём)."""
    stmt = (
        select(Category, func.count(StockItem.id))
        .outerjoin(StockItem, StockItem.category_id == Category.id)
        .group_by(Category.id)
        .order_by(func.lower(Category.name))
    )
    return [(cat, n) for cat, n in db.execute(stmt)]


def list_storage_locations_with_counts(db: Session) -> list[tuple[StorageLocation, int]]:
    stmt = (
        select(StorageLocation, func.count(StockItem.id))
        .outerjoin(StockItem, StockItem.storage_location_id == StorageLocation.id)
        .group_by(StorageLocation.id)
        .order_by(func.lower(StorageLocation.name))
    )
    return [(loc, n) for loc, n in db.execute(stmt)]


def find_category_by_name(db: Session, name: str) -> Optional[Category]:
    """Поиск категории по названию без учёта регистра. Нужен, чтобы не создать дубль «молочные»/«Молочные»."""
    return db.scalar(select(Category).where(func.lower(Category.name) == name.strip().lower()))


def find_storage_location_by_name(db: Session, name: str) -> Optional[StorageLocation]:
    return db.scalar(select(StorageLocation).where(func.lower(StorageLocation.name) == name.strip().lower()))


# ---- статистика для карточек сверху страницы ----
def get_stats(db: Session, today: Optional[date] = None) -> dict[str, int]:
    """{'total', 'fresh', 'expiring_soon', 'expired', 'no_date'} — одним запросом."""
    statuses = list(ExpiryStatus)
    row = db.execute(
        select(
            func.count(StockItem.id),
            *[func.count(case((StockItem.status_clause(s, today), 1))) for s in statuses],
        )
    ).one()
    return {"total": row[0], **{s.value: row[i + 1] for i, s in enumerate(statuses)}}
