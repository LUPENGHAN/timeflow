"""Plain domain structures kept independent from FastAPI and SQLAlchemy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from timeapp.domain.enums import (
    CommandAction,
    CommandEntity,
    DeliveryChannel,
    DomainEventType,
    ItemStatus,
    ItemType,
    ReminderPriority,
    ReminderStatus,
    ReminderTriggerType,
    VoiceCommandStatus,
    WriteRequestStatus,
)

JsonObject = dict[str, Any]


def utc_now() -> datetime:
    """Return a timezone-aware current timestamp."""

    return datetime.now(UTC)


@dataclass(slots=True)
class Identity:
    """User, device and session identifiers travelling with every command."""

    user_id: str
    device_id: str | None = None
    session_id: str | None = None


@dataclass(slots=True)
class Command:
    """Stable command model produced by ASR/parser or direct HTTP input."""

    id: str
    identity: Identity
    action: CommandAction
    entity: CommandEntity
    title: str | None = None
    description: str | None = None
    target_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: ReminderPriority = ReminderPriority.NORMAL
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    context: JsonObject = field(default_factory=dict)
    reference_context: JsonObject = field(default_factory=dict)
    payload: JsonObject = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class VoiceCommand:
    """ASR/parser audit record for one voice submission."""

    id: str
    identity: Identity
    transcript: str
    status: VoiceCommandStatus
    command_id: str | None = None
    error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class WriteRequest:
    """Confirmation gate that must precede every business write."""

    id: str
    identity: Identity
    source_command_id: str
    command: Command
    candidate_payload: JsonObject
    payload_hash: str
    expires_at: datetime
    idempotency_key: str
    status: WriteRequestStatus = WriteRequestStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class DomainEvent:
    """Append-only business fact and realtime sync source."""

    id: str
    event_type: DomainEventType
    aggregate_type: str
    aggregate_id: str
    version: int
    occurred_at: datetime
    payload: JsonObject


@dataclass(slots=True)
class Item:
    """Unified calendar/todo item used by P0 capabilities."""

    id: str
    user_id: str
    item_type: ItemType
    title: str
    description: str | None = None
    status: ItemStatus = ItemStatus.ACTIVE
    start_at: datetime | None = None
    end_at: datetime | None = None
    due_at: datetime | None = None
    place_text: str | None = None
    timezone: str = "UTC"
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Reminder:
    """P0 reminder rule bound to an item."""

    id: str
    user_id: str
    item_id: str
    trigger_type: ReminderTriggerType
    trigger_at: datetime | None = None
    place_id: str | None = None
    priority: ReminderPriority = ReminderPriority.NORMAL
    delivery_channel: DeliveryChannel = DeliveryChannel.LOCAL_NOTIFICATION
    status: ReminderStatus = ReminderStatus.PENDING
    snooze_count: int = 0
    last_triggered_at: datetime | None = None
    local_notification_id: str | None = None
    expires_at: datetime | None = None
    failed_reason: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    cancelled_at: datetime | None = None
