"""Shared FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from timeapp.ai.asr import AsrClient
from timeapp.ai.parser import LLMCommandParser, MockCommandParser
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import SqlAlchemyStore, WriteRequestMemoryStore
from timeapp.core.config import get_settings
from timeapp.core.db import SessionLocal
from timeapp.domain.models import Identity

# Write requests are not persisted to the database (see WriteRequestMemoryStore's
# docstring). SqlAlchemyStore is constructed fresh per request, so this bucket must
# be a module-level singleton shared across requests -- the same pattern
# `realtime_manager` (api/realtime.py) uses for WS connections.
_write_request_store = WriteRequestMemoryStore()


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_timeflow_app() -> Generator[TimeflowApplication, None, None]:
    """获取应用实例。"""

    session = SessionLocal()
    settings = get_settings()
    parser = (
        LLMCommandParser(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        if settings.llm_api_key
        else MockCommandParser()
    )
    try:
        store = SqlAlchemyStore(session, write_requests=_write_request_store)
        yield TimeflowApplication(store, parser=parser)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_identity() -> Identity:
    """获取当前身份。"""

    return Identity(user_id="demo-user", device_id="demo-device", session_id="demo-session")


def get_asr_client() -> AsrClient | None:
    """获取 ASR 客户端。"""

    settings = get_settings()
    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        return None
    return AsrClient(
        api_key=api_key,
        base_url=settings.asr_base_url,
        model=settings.asr_model,
        protocol=settings.asr_protocol,
        language=settings.asr_language,
    )
