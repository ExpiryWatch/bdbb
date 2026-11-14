import time
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Category, ExpiryStatus, StockItem, calc_status
from app.seed import seed_bulk, seed_demo

TODAY = date(2026, 11, 7)


def test_crud_and_timestamps(db):
    item = StockItem(name="Молоко", quantity=2, unit="л")
    db.add(item)
    db.commit()
    assert item.id and item.created_at and item.updated_at

    time.sleep(0.01)
    item.quantity = 1.5
    db.commit()
    db.refresh(item)
    assert item.quantity == 1.5 and item.updated_at > item.created_at

    db.delete(item)
    db.commit()
    assert db.get(StockItem, item.id) is None


def test_default_unit_and_text_cleanup(db):
    item = StockItem(name="  Соль  ", quantity=1, comment="   ")
    db.add(item)
    db.commit()
    assert item.unit == "шт"
    assert item.name == "Соль"      # пробелы по краям убраны
    assert item.comment is None     # пустой комментарий хранится как NULL


@pytest.mark.parametrize("kwargs", [
    {"name": "   ", "quantity": 1},
    {"name": "Хлеб", "quantity": 0},
    {"name": "Хлеб", "quantity": -1},
    {"name": "Хлеб", "quantity": 1, "purchase_date": TODAY, "expiry_date": TODAY - timedelta(days=1)},
])
def test_db_rejects_invalid_items(db, kwargs):
    db.add(StockItem(**kwargs))
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_accepts_boundary_values(db):
    db.add(StockItem(name="Ок", quantity=0.01, purchase_date=TODAY, expiry_date=TODAY))  # срок = дата покупки допустим
    db.add(StockItem(name="Без дат", quantity=1))
    db.commit()


@pytest.mark.parametrize("offset,expected", [
    (None, ExpiryStatus.NO_DATE),
    (-1, ExpiryStatus.EXPIRED),
    (0, ExpiryStatus.EXPIRING_SOON),
    (3, ExpiryStatus.EXPIRING_SOON),
    (4, ExpiryStatus.FRESH),
])
def test_status_boundaries(offset, expected):
    expiry = None if offset is None else TODAY + timedelta(days=offset)
    assert calc_status(expiry, TODAY) is expected


def test_sql_status_filter_matches_python_status(db):
    for off in [None, -10, -1, 0, 1, 3, 4, 100]:
        db.add(StockItem(name=f"i{off}", quantity=1, expiry_date=None if off is None else TODAY + timedelta(days=off)))
    db.commit()
    for status in ExpiryStatus:
        from_sql = {i.id for i in db.scalars(select(StockItem).where(StockItem.status_clause(status, TODAY)))}
        from_py = {i.id for i in db.scalars(select(StockItem)) if calc_status(i.expiry_date, TODAY) is status}
        assert from_sql == from_py, status


def test_search_ignores_case_and_yo_and_escapes_wildcards(db):
    db.add_all([StockItem(name="Молоко", quantity=1), StockItem(name="Йогурт", quantity=1),
                StockItem(name="Мёд", quantity=1), StockItem(name="100% сок", quantity=1)])
    db.commit()
    find = lambda q: {i.name for i in db.scalars(select(StockItem).where(StockItem.search_clause(q)))}  # noqa: E731
    assert find("МОЛ") == {"Молоко"}
    assert find("гурт") == {"Йогурт"}
    assert find("мед") == {"Мёд"} and find("мёд") == {"Мёд"}
    assert find("%") == {"100% сок"}  # спецсимвол LIKE не работает как маска


def test_names_are_unique(db):
    db.add(Category(name="Крупы"))
    db.commit()
    db.add(Category(name="Крупы"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_seed_demo_has_all_statuses(db):
    seed_demo(db)
    db.commit()
    assert {i.status for i in db.scalars(select(StockItem))} == set(ExpiryStatus)


def test_seed_is_idempotent(db):
    from app.seed import seed_extended
    for _ in range(2):
        seed_demo(db)
        seed_extended(db)
        db.commit()
    assert len(db.scalars(select(StockItem)).all()) == 21
