"""Тестовые данные.

    python -m app.seed                   # справочники + 6 позиций из макета (все 4 статуса)
    python -m app.seed --extended        # + 15 позиций для проверки фильтров, сортировки и граничных случаев
    python -m app.seed --bulk 1000       # + N случайных позиций (проверка производительности)
    python -m app.seed --reset           # пересоздать таблицы перед заполнением

Даты считаются от сегодняшнего дня, поэтому статусы всегда соответствуют задуманным.
"""
import argparse
import random
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.init_db import init_db
from app.models import Category, StockItem, StorageLocation

CATEGORIES = [
    "Молочные продукты", "Хлебобулочные изделия", "Крупы и макароны",
    "Фрукты и овощи", "Бакалея", "Мясо и рыба",
    "Напитки",  # пустая категория: проверка справочников без позиций
]
LOCATIONS = [
    ("Холодильник", "snowflake"), ("Морозильная камера", "freezer"), ("Кухонный шкаф", "cabinet"),
    ("Балкон", "balcony"),  # пустое место хранения
]


def _get_or_create_refs(db: Session) -> tuple[dict[str, Category], dict[str, StorageLocation]]:
    cats = {c.name: c for c in db.scalars(select(Category))}
    for name in CATEGORIES:
        if name not in cats:
            cats[name] = Category(name=name)
            db.add(cats[name])
    locs = {l.name: l for l in db.scalars(select(StorageLocation))}
    for name, icon in LOCATIONS:
        if name not in locs:
            locs[name] = StorageLocation(name=name, icon=icon)
            db.add(locs[name])
    db.flush()
    return cats, locs


def seed_demo(db: Session, today: Optional[date] = None) -> None:
    """6 позиций из макета: Годен ×2, Скоро истекает ×2, Просрочено ×1, Срок не указан ×1."""
    today = today or date.today()
    cats, locs = _get_or_create_refs(db)
    if db.scalar(select(StockItem.id).limit(1)) is not None:
        return  # данные уже есть, повторно не добавляем
    d = lambda offset: today + timedelta(days=offset)  # noqa: E731
    fridge, shelf = locs["Холодильник"], locs["Кухонный шкаф"]
    db.add_all([
        StockItem(name="Молоко", quantity=2, unit="л", category=cats["Молочные продукты"], storage_location=fridge,
                  purchase_date=d(-2), expiry_date=d(10)),                       # Годен
        StockItem(name="Йогурт", quantity=4, unit="шт", category=cats["Молочные продукты"], storage_location=fridge,
                  purchase_date=d(-5), expiry_date=d(2)),                        # Скоро истекает
        StockItem(name="Хлеб", quantity=1, unit="шт", category=cats["Хлебобулочные изделия"], storage_location=shelf,
                  purchase_date=d(-7), expiry_date=d(-3), comment="Нарезной"),   # Просрочено
        StockItem(name="Рис", quantity=2, unit="кг", category=cats["Крупы и макароны"], storage_location=shelf,
                  purchase_date=d(-30), expiry_date=d(400)),                     # Годен
        StockItem(name="Яблоки", quantity=1, unit="кг", category=cats["Фрукты и овощи"], storage_location=fridge,
                  purchase_date=d(-4), expiry_date=d(3)),                        # Скоро истекает (граница: ровно 3 дня)
        StockItem(name="Соль", quantity=1, unit="кг", category=cats["Бакалея"], storage_location=shelf),  # Срок не указан
    ])


# (название, кол-во, ед., категория, место, дней от сегодня до покупки, дней до срока, комментарий)
_EXTENDED = [
    ("Сыр",              0.3, "кг",  "Молочные продукты",     "Холодильник",        -10,   0, "Граница: срок истекает сегодня"),
    ("Сметана",          1,   "шт",  "Молочные продукты",     "Холодильник",         -3,   4, "Граница: осталось 4 дня, уже «Годен»"),
    ("Творог",           0.5, "кг",  "Молочные продукты",     "Холодильник",         -8,  -1, "Граница: просрочен вчера"),
    ("Батон",            1,   "шт",  "Хлебобулочные изделия", "Кухонный шкаф",       -3,   1, None),
    ("Курица",           1.2, "кг",  "Мясо и рыба",           "Морозильная камера",  -2,  90, None),
    ("Пельмени",         2,   "уп",  "Мясо и рыба",           "Морозильная камера", -15, 180, None),
    ("Лосось",           0.8, "кг",  "Мясо и рыба",           "Морозильная камера", -20, -10, None),
    ("Макароны",         3,   "уп",  "Крупы и макароны",      "Кухонный шкаф",      -40, 300, None),
    ("Гречка",           1,   "кг",  "Крупы и макароны",      "Кухонный шкаф",      -60, None, "Срок не указан"),
    ("Морковь",          2,   "кг",  "Фрукты и овощи",        "Холодильник",         -6,  14, None),
    ("Ежевика",          0.4, "кг",  "Фрукты и овощи",        "Морозильная камера",  -5,  60, None),
    ("апельсины",        1.5, "кг",  "Фрукты и овощи",        "Холодильник",         -4,   5, "Название с маленькой буквы (проверка сортировки)"),
    ("Мёд",              0.5, "кг",  None,                    "Кухонный шкаф",     None, None, "Без категории; буква «ё» (проверка поиска «мед»)"),
    ("Консервы",         4,   "шт",  "Бакалея",               None,                 -30, 500, "Без места хранения"),
    ("Молоко кокосовое", 1,   "л",   "Бакалея",               "Кухонный шкаф",      -12, 200, "Второе «молоко» в другой категории (проверка поиска)"),
]


def seed_extended(db: Session, today: Optional[date] = None) -> None:
    """15 дополнительных позиций: все категории и места, граничные сроки, позиции без категории/места."""
    today = today or date.today()
    cats, locs = _get_or_create_refs(db)
    if db.scalar(select(StockItem.id).where(StockItem.name == "Сыр")) is not None:
        return
    off = lambda n: None if n is None else today + timedelta(days=n)  # noqa: E731
    for name, qty, unit, cat, loc, p_off, e_off, comment in _EXTENDED:
        db.add(StockItem(
            name=name, quantity=qty, unit=unit,
            category=cats[cat] if cat else None, storage_location=locs[loc] if loc else None,
            purchase_date=off(p_off), expiry_date=off(e_off), comment=comment,
        ))


def seed_bulk(db: Session, n: int, today: Optional[date] = None) -> None:
    today = today or date.today()
    rng = random.Random(42)
    cats, locs = _get_or_create_refs(db)
    cat_list, loc_list = list(cats.values()), list(locs.values())
    units = ["шт", "кг", "г", "л", "мл", "уп"]
    items = []
    for i in range(n):
        purchase = today - timedelta(days=rng.randint(0, 60))
        expiry = None if rng.random() < 0.1 else purchase + timedelta(days=rng.randint(0, 120))
        items.append(StockItem(
            name=f"Продукт {i + 1}", quantity=round(rng.uniform(0.1, 20), 2), unit=rng.choice(units),
            category=rng.choice(cat_list), storage_location=rng.choice(loc_list),
            purchase_date=purchase, expiry_date=expiry,
        ))
    db.add_all(items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="пересоздать все таблицы")
    parser.add_argument("--extended", action="store_true", help="добавить расширенный набор (15 позиций)")
    parser.add_argument("--bulk", type=int, default=0, help="добавить N случайных позиций")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as session:
        seed_demo(session)
        if args.extended:
            seed_extended(session)
        if args.bulk:
            seed_bulk(session, args.bulk)
        session.commit()
    print("Готово.")
