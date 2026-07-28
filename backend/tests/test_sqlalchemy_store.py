"""Tests for SQLAlchemy-backed store transaction behavior."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from timeapp.application.service import TimeflowApplication
from timeapp.application.store import SqlAlchemyStore, WriteRequestMemoryStore
from timeapp.core.db import Base
from timeapp.domain.enums import ItemType
from timeapp.domain.models import Identity
from timeapp.infrastructure.models import ItemRecord


def test_sqlalchemy_store_flushes_without_auto_commit() -> None:
    """Outer transaction rollback should remove item and event writes."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        store = SqlAlchemyStore(session, write_requests=WriteRequestMemoryStore())
        app = TimeflowApplication(store)
        app.create_item(
            identity=Identity(user_id="demo-user"),
            item_type=ItemType.TODO,
            title="只 flush 不 commit",
        )
        assert session.scalars(select(ItemRecord)).all()
        session.rollback()

    with Session(engine) as session:
        assert session.scalars(select(ItemRecord)).all() == []
