"""Подключение к БД и базовый класс моделей.

По умолчанию используется SQLite-файл pantry.db (данные переживают перезапуск).
Для PostgreSQL достаточно задать переменную окружения, например:
    DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/pantry
"""
import os
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pantry.db")


class Base(DeclarativeBase):
    """Базовый класс всех моделей."""


def _py_lower(value):
    # Встроенный lower() в SQLite понимает только ASCII, поэтому «Молоко» и «молоко»
    # не совпали бы при поиске. Подменяем функцию на Unicode-вариант.
    return value.lower() if isinstance(value, str) else value


def _sqlite_on_connect(dbapi_conn, _record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")  # в SQLite внешние ключи по умолчанию выключены
    cursor.close()
    dbapi_conn.create_function("lower", 1, _py_lower, deterministic=True)


def make_engine(url: str = DATABASE_URL) -> Engine:
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # одна общая in-memory БД (для тестов)
    engine = create_engine(url, **kwargs)
    if is_sqlite:
        event.listen(engine, "connect", _sqlite_on_connect)
    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: `db: Session = Depends(get_db)`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
