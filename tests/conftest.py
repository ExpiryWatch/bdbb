from datetime import date

import pytest
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.database import Base, make_engine
from app.seed import seed_demo, seed_extended


@pytest.fixture()
def today() -> date:
    return date.today()


@pytest.fixture()
def db():
    engine = make_engine("sqlite://")  # чистая БД в памяти для каждого теста
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture()
def seeded(db, today):
    """БД с 21 позицией: 6 из макета + 15 расширенных."""
    seed_demo(db, today)
    seed_extended(db, today)
    db.commit()
    return db
