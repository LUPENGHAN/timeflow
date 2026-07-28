"""SQLAlchemy models for the MS1 architecture baseline."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timeapp.core.db import Base


class DomainEventRecord(Base):
    """Append-only domain events used by projections, WS and audit."""

    __tablename__ = "domain_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class ItemRecord(Base):
    """Unified calendar/todo table."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    item_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), index=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    place_text: Mapped[str | None] = mapped_column(String(256))
    place_type: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[str | None] = mapped_column(String(64))
    longitude: Mapped[str | None] = mapped_column(String(64))
    accuracy_meters: Mapped[int | None] = mapped_column(Integer)
    radius_meters: Mapped[int] = mapped_column(Integer, default=100)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reminders: Mapped[list[ReminderRecord]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class ReminderRecord(Base):
    """Reminder table bound to items."""

    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(64), index=True)
    trigger_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[str] = mapped_column(String(32))
    delivery_channel: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), index=True)
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_notification_id: Mapped[str | None] = mapped_column(String(128))
    local_registration_status: Mapped[str] = mapped_column(String(64), default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_reason: Mapped[str | None] = mapped_column(Text)
    fallback_status: Mapped[str] = mapped_column(String(64), default="not_required")
    fallback_after_seconds: Mapped[int] = mapped_column(Integer, default=300)
    fallback_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    item: Mapped[ItemRecord] = relationship(back_populates="reminders")


class ReminderRuleRecord(Base):
    """Backing table for `RepeatRule` (daily/weekdays/custom_weekdays repeat rules)."""

    __tablename__ = "reminder_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    item_id: Mapped[str | None] = mapped_column(String(36), index=True)
    rule_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
