"""Целостность связанных данных: создание, изменение, удаление."""
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import queries as q
from app.database import Base, make_engine
from app.models import Category, StockItem, StorageLocation


def total(db):
    return db.scalar(select(func.count()).select_from(StockItem))


def snapshot(db):
    db.expire_all()  # перечитываем из БД, а не из кэша сессии
    return {
        i.id: (i.name, i.quantity, i.unit, i.category_id, i.storage_location_id,
               i.purchase_date, i.expiry_date, i.comment, i.updated_at)
        for i in db.scalars(select(StockItem))
    }


# ---------- создание ----------
def test_create_item_with_relationships_and_back_references(db):
    cat, loc = Category(name="Молочные"), StorageLocation(name="Холодильник")
    db.add(StockItem(name="Молоко", quantity=2, unit="л", category=cat, storage_location=loc))
    db.commit()
    assert [i.name for i in cat.items] == ["Молоко"] and [i.name for i in loc.items] == ["Молоко"]


def test_create_item_by_ids_like_api_does(seeded):
    db = seeded
    item = StockItem(name="Кефир", quantity=1, unit="л",
                     category_id=q.find_category_by_name(db, "Молочные продукты").id,
                     storage_location_id=q.find_storage_location_by_name(db, "Холодильник").id)
    db.add(item)
    db.commit()
    db.refresh(item)
    assert item.category.name == "Молочные продукты" and total(db) == 22


def test_item_with_nonexistent_category_or_location_is_rejected(db):
    for kwargs in ({"category_id": 9999}, {"storage_location_id": 9999}):
        db.add(StockItem(name="X", quantity=1, **kwargs))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ---------- изменение ----------
def test_update_moves_item_between_categories_and_clears_them(seeded):
    db = seeded
    item = q.list_items(db, q="сыр")[0]
    old_cat_count = dict((c.name, n) for c, n in q.list_categories_with_counts(db))

    item.category = q.find_category_by_name(db, "Бакалея")
    db.commit()
    counts = dict((c.name, n) for c, n in q.list_categories_with_counts(db))
    assert counts["Молочные продукты"] == old_cat_count["Молочные продукты"] - 1
    assert counts["Бакалея"] == old_cat_count["Бакалея"] + 1

    item.category = None
    item.storage_location = None
    db.commit()
    db.refresh(item)
    assert item.category_id is None and item.storage_location_id is None


def test_rename_category_is_visible_in_items_and_cannot_duplicate(seeded):
    db = seeded
    cat = q.find_category_by_name(db, "Молочные продукты")
    cat.name = "Молочка"
    db.commit()
    assert {i.category.name for i in q.list_items(db, category_id=cat.id)} == {"Молочка"}

    cat.name = "Бакалея"  # такое название уже занято
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invalid_update_is_rejected_and_old_value_is_kept(seeded):
    db = seeded
    item = q.list_items(db, q="сыр")[0]
    old_qty = item.quantity
    item.quantity = 0
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.refresh(item)
    assert item.quantity == old_qty
    item.quantity = 5  # сессия после ошибки продолжает работать
    db.commit()


def test_update_touches_updated_at_only_for_changed_item(seeded):
    db = seeded
    before = snapshot(db)
    time.sleep(0.01)
    item = q.list_items(db, q="сыр")[0]
    item.comment = "Новый комментарий"
    db.commit()
    after = snapshot(db)
    assert after[item.id][8] > before[item.id][8]
    assert all(after[k] == before[k] for k in before if k != item.id)


# ---------- удаление ----------
def test_delete_item_keeps_other_items_and_references(seeded):
    db = seeded
    before = snapshot(db)
    target = q.list_items(db, q="молоко", category_id=q.find_category_by_name(db, "Молочные продукты").id)[0]
    target_id, cat_id, loc_id = target.id, target.category_id, target.storage_location_id

    db.delete(target)
    db.commit()
    after = snapshot(db)

    assert set(before) - set(after) == {target_id}
    assert all(after[k] == before[k] for k in after)  # остальные записи не изменились
    assert db.get(Category, cat_id) and db.get(StorageLocation, loc_id)  # справочники остались


def test_cannot_delete_category_or_location_in_use_and_nothing_breaks(seeded):
    db = seeded
    before = snapshot(db)
    for obj in (q.find_category_by_name(db, "Молочные продукты"), q.find_storage_location_by_name(db, "Холодильник")):
        db.delete(obj)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.get(type(obj), obj.id) is not None
    assert snapshot(db) == before and total(db) == 21


def test_category_can_be_deleted_after_items_are_moved_or_removed(seeded):
    db = seeded
    dairy = q.find_category_by_name(db, "Молочные продукты")
    for item in q.get_items_by_category(db, dairy.id):
        item.category = None  # «освобождаем» категорию
    db.commit()
    db.delete(dairy)
    db.commit()
    assert q.find_category_by_name(db, "Молочные продукты") is None
    assert total(db) == 21  # позиции никуда не делись


def test_unused_category_and_location_can_be_deleted(seeded):
    db = seeded
    for obj in (q.find_category_by_name(db, "Напитки"), q.find_storage_location_by_name(db, "Балкон")):
        db.delete(obj)
    db.commit()
    assert q.find_category_by_name(db, "Напитки") is None


# ---------- устойчивость ----------
def test_failed_operation_does_not_damage_other_data(seeded):
    db = seeded
    before = snapshot(db)
    for bad in (dict(name="", quantity=1), dict(name="A", quantity=-5), dict(name="B", quantity=1, category_id=424242)):
        db.add(StockItem(**bad))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert snapshot(db) == before
    db.add(StockItem(name="Новая", quantity=1))  # после ошибок БД работает как обычно
    db.commit()
    assert total(db) == 22


def test_data_survives_restart(tmp_path):
    url = f"sqlite:///{(tmp_path / 'pantry_test.db').as_posix()}"

    engine1 = make_engine(url)
    Base.metadata.create_all(engine1)
    with Session(engine1) as s:
        cat = Category(name="Молочные")
        s.add(StockItem(name="Молоко", quantity=2, unit="л", category=cat))
        s.commit()
    engine1.dispose()  # «выключили приложение»

    engine2 = make_engine(url)  # «запустили снова»
    with Session(engine2) as s:
        item = s.scalars(select(StockItem)).one()
        assert (item.name, item.quantity, item.unit, item.category.name) == ("Молоко", 2, "л", "Молочные")
    engine2.dispose()
