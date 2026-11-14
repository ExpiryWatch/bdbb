"""Создание таблиц с нуля:  python -m app.init_db"""
from app import models  # noqa: F401  (регистрирует модели в Base.metadata)
from app.database import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Таблицы созданы:", ", ".join(Base.metadata.tables))
