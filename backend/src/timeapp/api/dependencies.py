"""Shared FastAPI dependencies."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from timeapp.application.service import TimeflowApplication
from timeapp.core.db import SessionLocal
from timeapp.domain.models import Identity


def get_db() -> Generator[Session, None, None]:
    """提供一个请求范围内的数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@lru_cache
def get_timeflow_app() -> TimeflowApplication:
    """Return the process-local application service.

    Repository-backed storage can replace this dependency without changing the
    HTTP or WebSocket routes.
    """

    return TimeflowApplication()


def get_identity() -> Identity:
    """Return a development identity until auth is introduced."""

    return Identity(user_id="demo-user", device_id="demo-device", session_id="demo-session")
