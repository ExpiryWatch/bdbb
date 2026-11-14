import time

import pytest

from app import queries as q
from app.models import ExpiryStatus
from app.seed import seed_bulk

names = lambda items: [i.name for i in items]  # noqa: E731


def cat_id(db, name):
    return q.find_category_by_name(db, name).id


def loc_id(db, name):
    return q.find_storage_location_by_name(db, name).id


# ---------- получение по категории и месту хранения ----------
def test_items_by_category(seeded):
    db = seeded
    assert set(names(q.get_items_by_category(db, cat_id(db, "Молочные продукты")))) == {
        "Молоко", "Йогурт", "Сыр", "Сметана", "Творог"}
    assert set(names(q.get_items_by_category(db, cat_id(db, "Мясо и рыба")))) == {"Курица", "Пельмени", "Лосось"}
    assert q.get_items_by_category(db, cat_id(db, "Напитки")) == []  # пустая категория
    assert q.get_items_by_category(db, 99999) == []                   # несуществующая


def test_items_by_storage_location(seeded):
    db = seeded
    assert set(names(q.get_items_by_storage_location(db, loc_id(db, "Морозильная камера")))) == {
        "Курица", "Пельмени", "Лосось", "Ежевика"}
    assert len(q.get_items_by_storage_location(db, loc_id(db, "Холодильник"))) == 8
    assert len(q.get_items_by_storage_location(db, loc_id(db, "Кухонный шкаф"))) == 8
    assert q.get_items_by_storage_location(db, loc_id(db, "Балкон")) == []


def test_items_by_category_and_location(seeded):
    db = seeded
    fruits = cat_id(db, "Фрукты и овощи")
    assert set(names(q.get_items_by_category_and_location(db, fruits, loc_id(db, "Холодильник")))) == {
        "Яблоки", "Морковь", "апельсины"}
    assert names(q.get_items_by_category_and_location(db, fruits, loc_id(db, "Морозильная камера"))) == ["Ежевика"]


def test_related_objects_are_loaded(seeded):
    item = q.list_items(seeded, q="сыр")[0]
    assert item.category.name == "Молочные продукты" and item.storage_location.name == "Холодильник"


def test_items_without_category_or_location_are_listed(seeded):
    all_items = q.list_items(seeded)
    assert len(all_items) == 21
    assert next(i for i in all_items if i.name == "Мёд").category is None
    assert next(i for i in all_items if i.name == "Консервы").storage_location is None


# ---------- поиск и фильтр по статусу ----------
def test_search(seeded, today):
    db = seeded
    assert set(names(q.list_items(db, q="молоко"))) == {"Молоко", "Молоко кокосовое"}
    assert set(names(q.list_items(db, q="МОЛОКО"))) == {"Молоко", "Молоко кокосовое"}
    assert names(q.list_items(db, q="мед")) == ["Мёд"]
    assert set(names(q.list_items(db, q="ог"))) == {"Йогурт", "Творог"}
    assert q.list_items(db, q="несуществующий") == []
    assert len(q.list_items(db, q="   ")) == 21  # пустой запрос = без поиска
    assert names(q.list_items(db, q="молоко", category_id=cat_id(db, "Молочные продукты"))) == ["Молоко"]


def test_status_filter_and_stats(seeded, today):
    db = seeded
    expected = {"fresh": 11, "expiring_soon": 4, "expired": 3, "no_date": 3}
    for status, n in expected.items():
        items = q.list_items(db, status=status, today=today)
        assert len(items) == n and all(i.status.value == status for i in items)
        assert q.count_items(db, status=status, today=today) == n
    assert q.get_stats(db, today) == {"total": 21, **expected}
    assert names(q.list_items(db, status=ExpiryStatus.EXPIRED, category_id=cat_id(db, "Мясо и рыба"))) == ["Лосось"]


def test_boundary_items_get_expected_statuses(seeded):
    by_name = {i.name: i for i in q.list_items(seeded)}
    assert (by_name["Сыр"].days_left, by_name["Сыр"].status) == (0, ExpiryStatus.EXPIRING_SOON)
    assert (by_name["Яблоки"].days_left, by_name["Яблоки"].status) == (3, ExpiryStatus.EXPIRING_SOON)
    assert (by_name["Сметана"].days_left, by_name["Сметана"].status) == (4, ExpiryStatus.FRESH)
    assert (by_name["Творог"].days_left, by_name["Творог"].status) == (-1, ExpiryStatus.EXPIRED)


def test_count_matches_list_with_filters(seeded):
    db = seeded
    kwargs = dict(q="о", storage_location_id=loc_id(db, "Холодильник"))
    assert q.count_items(db, **kwargs) == len(q.list_items(db, **kwargs))


# ---------- сортировка ----------
def test_sort_by_name_is_case_insensitive_and_handles_yo(seeded):
    result = names(q.list_items(seeded, sort="name"))
    assert result[0] == "апельсины" and result[-1] == "Яблоки"  # регистр не влияет
    assert result == sorted(result, key=lambda n: n.lower().replace("ё", "е"))
    assert result.index("Макароны") < result.index("Мёд") < result.index("Молоко")  # «ё» как «е»
    assert names(q.list_items(seeded, sort="name", order="desc")) == result[::-1]


def test_sort_by_expiry_asc_puts_missing_dates_last(seeded):
    assert names(q.list_items(seeded, sort="expiry")) == [
        "Лосось", "Хлеб", "Творог", "Сыр", "Батон", "Йогурт", "Яблоки", "Сметана", "апельсины", "Молоко",
        "Морковь", "Ежевика", "Курица", "Пельмени", "Молоко кокосовое", "Макароны", "Рис", "Консервы",
        "Гречка", "Мёд", "Соль",  # без срока, между собой по названию
    ]


def test_sort_by_expiry_desc_still_puts_missing_dates_last(seeded):
    assert names(q.list_items(seeded, sort="expiry", order="desc")) == [
        "Консервы", "Рис", "Макароны", "Молоко кокосовое", "Пельмени", "Курица", "Ежевика", "Морковь", "Молоко",
        "апельсины", "Сметана", "Яблоки", "Йогурт", "Батон", "Сыр", "Творог", "Хлеб", "Лосось",
        "Гречка", "Мёд", "Соль",
    ]


def test_sort_works_together_with_filters(seeded):
    db = seeded
    result = q.list_items(db, category_id=cat_id(db, "Молочные продукты"), sort="expiry")
    assert names(result) == ["Творог", "Сыр", "Йогурт", "Сметана", "Молоко"]


def test_invalid_sort_arguments_raise(seeded):
    with pytest.raises(ValueError):
        q.list_items(seeded, sort="price")
    with pytest.raises(ValueError):
        q.list_items(seeded, order="up")


def test_pagination_is_consistent_with_full_list(seeded):
    full = names(q.list_items(seeded, sort="name"))
    assert names(q.list_items(seeded, sort="name", limit=5, offset=5)) == full[5:10]


# ---------- справочники ----------
def test_categories_and_locations_with_counts(seeded):
    cats = {c.name: n for c, n in q.list_categories_with_counts(seeded)}
    assert cats == {"Молочные продукты": 5, "Хлебобулочные изделия": 2, "Крупы и макароны": 3,
                    "Фрукты и овощи": 4, "Бакалея": 3, "Мясо и рыба": 3, "Напитки": 0}
    locs = {l.name: n for l, n in q.list_storage_locations_with_counts(seeded)}
    assert locs == {"Холодильник": 8, "Морозильная камера": 4, "Кухонный шкаф": 8, "Балкон": 0}


def test_find_by_name_ignores_case_and_spaces(seeded):
    assert q.find_category_by_name(seeded, "  молочные ПРОДУКТЫ ").name == "Молочные продукты"
    assert q.find_category_by_name(seeded, "нет такой") is None


# ---------- производительность ----------
def test_1000_items_list_search_filter_sort_under_2s(db):
    seed_bulk(db, 1000)
    db.commit()
    start = time.perf_counter()
    all_items = q.list_items(db, sort="name")
    found = q.list_items(db, q="продукт 1", status="fresh", category_id=1, sort="expiry")
    stats = q.get_stats(db)
    elapsed = time.perf_counter() - start
    assert len(all_items) == 1000 and stats["total"] == 1000
    assert elapsed < 2, f"слишком медленно: {elapsed:.2f} с"
    assert found is not None
