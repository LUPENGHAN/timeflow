"""Shared FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from timeapp.application.service import TimeflowApplication
from timeapp.application.store import SqlAlchemyStore
from timeapp.core.db import SessionLocal
from timeapp.domain.models import Identity


def get_db() -> Generator[Session, None, None]:
    """提供一个请求范围内的数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_timeflow_app() -> Generator[TimeflowApplication, None, None]:
    """Return the process-local application service.

    The API runtime uses the configured SQLAlchemy database. Tests can override
    this dependency with an in-memory application instance.
    """

    session = SessionLocal()
    try:
        yield TimeflowApplication(SqlAlchemyStore(session))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_identity() -> Identity:
    """Return a development identity until auth is introduced."""

    return Identity(user_id="demo-user", device_id="demo-device", session_id="demo-session")
