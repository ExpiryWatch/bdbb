"""Показывает результат запросов на текущей БД:  python -m app.seed --extended && python -m app.demo_queries"""
from app import queries as q
from app.database import SessionLocal
from app.models import ExpiryStatus, STATUS_LABELS, StockItem


def show(title: str, items: list[StockItem]) -> None:
    print(f"\n== {title} ({len(items)})")
    for i in items:
        cat = i.category.name if i.category else "—"
        loc = i.storage_location.name if i.storage_location else "—"
        days = "нет срока" if i.days_left is None else f"{i.days_left:>4} дн."
        print(f"  {i.name:<18} {i.quantity:>5} {i.unit:<3} | {cat:<22} | {loc:<19} | {days} | {i.status_label}")


with SessionLocal() as db:
    print("Статистика:", q.get_stats(db))

    print("\nКатегории:", [(c.name, n) for c, n in q.list_categories_with_counts(db)])
    print("Места хранения:", [(l.name, n) for l, n in q.list_storage_locations_with_counts(db)])

    dairy = q.find_category_by_name(db, "молочные ПРОДУКТЫ")
    fridge = q.find_storage_location_by_name(db, "холодильник")
    show("По категории «Молочные продукты»", q.get_items_by_category(db, dairy.id))
    show("По месту «Холодильник»", q.get_items_by_storage_location(db, fridge.id))
    show("Категория + место: Фрукты и овощи в холодильнике",
         q.get_items_by_category_and_location(db, q.find_category_by_name(db, "Фрукты и овощи").id, fridge.id))

    show("Сортировка по названию (А-Я)", q.list_items(db, sort="name"))
    show("Сортировка по сроку годности (ближайшие сверху, без срока в конце)", q.list_items(db, sort="expiry"))
    show("Сортировка по сроку годности (по убыванию)", q.list_items(db, sort="expiry", order="desc"))
    show("Поиск «МЕД»", q.list_items(db, q="МЕД"))
    show("Поиск «молоко»", q.list_items(db, q="молоко"))
    for s in ExpiryStatus:
        show(f"Фильтр по статусу «{STATUS_LABELS[s]}»", q.list_items(db, status=s, sort="expiry"))
