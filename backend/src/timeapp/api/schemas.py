"""Pydantic request and response models for the P0 API skeleton."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from timeapp.domain.models import (
    DomainEvent,
    Item,
    Reminder,
    RepeatRule,
    VoiceCommand,
    WriteRequest,
)

Weekday = Annotated[int, Field(ge=1, le=7)]
RepeatPatternValue = Literal["daily", "weekdays", "custom_weekdays"]
RepeatSeriesStatusValue = Literal["active", "paused", "stopped"]


class VoiceCommandCreateRequest(BaseModel):
    """Create a voice command from an existing transcript."""

    transcript: str = Field(min_length=1)


class VoiceCommandResponse(BaseModel):
    """Voice command audit response."""

    id: str
    transcript: str
    status: str
    command_id: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, voice_command: VoiceCommand) -> VoiceCommandResponse:
        """从领域对象构造响应对象。"""
        return cls(
            id=voice_command.id,
            transcript=voice_command.transcript,
            status=voice_command.status.value,
            command_id=voice_command.command_id,
            created_at=voice_command.created_at,
        )


class WriteRequestResponse(BaseModel):
    """Write request response shown in a confirmation card."""

    id: str
    source_command_id: str
    status: str
    candidate_payload: dict[str, Any]
    payload_hash: str
    expires_at: datetime
    created_at: datetime

    @classmethod
    def from_domain(cls, write_request: WriteRequest) -> WriteRequestResponse:
        """从领域对象构造响应对象。"""
        return cls(
            id=write_request.id,
            source_command_id=write_request.source_command_id,
            status=write_request.status.value,
            candidate_payload=write_request.candidate_payload,
            payload_hash=write_request.payload_hash,
            expires_at=write_request.expires_at,
            created_at=write_request.created_at,
        )


class EventResponse(BaseModel):
    """Domain event response used by HTTP sync and WS messages."""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    version: int
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def from_domain(cls, event: DomainEvent) -> EventResponse:
        """从领域对象构造响应对象。"""
        return cls(
            event_id=event.id,
            event_type=event.event_type.value,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            version=event.version,
            occurred_at=event.occurred_at,
            payload=event.payload,
        )


class VoiceCommandCreateResponse(BaseModel):
    """Response after transcript or audio command intake."""

    voice_command: VoiceCommandResponse
    write_request: WriteRequestResponse | None
    events: list[EventResponse]
    clarification: str | None = None
    candidates: list[ItemResponse] = Field(default_factory=list)


class ConfirmationResponse(BaseModel):
    """Response after confirm/reject actions."""

    write_request: WriteRequestResponse
    events: list[EventResponse]


class WriteRequestCreateRequest(BaseModel):
    """Create a pending write request from a candidate payload."""

    source_command_id: str
    candidate_payload: dict[str, Any]


class WriteRequestCreateResponse(BaseModel):
    """Pending write request creation response."""

    write_request: WriteRequestResponse
    events: list[EventResponse]


class WriteRequestUpdateRequest(BaseModel):
    """Update editable pending write-request payload fields."""

    candidate_payload: dict[str, Any]


class ItemResponse(BaseModel):
    """Calendar/todo item response."""

    id: str
    type: str
    title: str
    description: str | None
    status: str
    start_at: datetime | None
    end_at: datetime | None
    due_at: datetime | None
    place_text: str | None
    place_type: str | None
    latitude: str | None
    longitude: str | None
    accuracy_meters: int | None
    radius_meters: int
    version: int
    updated_at: datetime
    reminders: list[ReminderResponse] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, item: Item, reminders: list[Reminder] | None = None) -> ItemResponse:
        """从领域对象构造响应对象。"""
        return cls(
            id=item.id,
            type=item.item_type.value,
            title=item.title,
            description=item.description,
            status=item.status.value,
            start_at=item.start_at,
            end_at=item.end_at,
            due_at=item.due_at,
            place_text=item.place_text,
            place_type=item.place_type,
            latitude=item.latitude,
            longitude=item.longitude,
            accuracy_meters=item.accuracy_meters,
            radius_meters=item.radius_meters,
            version=item.version,
            updated_at=item.updated_at,
            reminders=[ReminderResponse.from_domain(reminder) for reminder in reminders or []],
        )


class ItemCreateRequest(BaseModel):
    """Create a manual calendar or todo item."""

    type: str
    title: str = Field(min_length=1)
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    due_at: datetime | None = None
    place_text: str | None = None
    place_type: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    accuracy_meters: int | None = None
    radius_meters: int = 100


class ItemCreateResponse(BaseModel):
    """Created item response."""

    item: ItemResponse
    events: list[EventResponse]


class ItemUpdateRequest(BaseModel):
    """Update editable calendar/todo fields."""

    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    due_at: datetime | None = None
    place_text: str | None = None
    place_type: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    accuracy_meters: int | None = None
    radius_meters: int | None = None


class ItemMutationResponse(BaseModel):
    """Updated item response."""

    item: ItemResponse
    events: list[EventResponse]


class ReminderResponse(BaseModel):
    """Reminder response bound to an item."""

    id: str
    item_id: str
    trigger_type: str
    trigger_at: datetime | None
    priority: str
    delivery_channel: str
    status: str
    snooze_count: int
    local_notification_id: str | None
    local_registration_status: str
    failed_reason: str | None
    fallback_status: str
    fallback_after_seconds: int
    fallback_requested_at: datetime | None
    version: int

    @classmethod
    def from_domain(cls, reminder: Reminder) -> ReminderResponse:
        """从领域对象构造响应对象。"""
        return cls(
            id=reminder.id,
            item_id=reminder.item_id,
            trigger_type=reminder.trigger_type.value,
            trigger_at=reminder.trigger_at,
            priority=reminder.priority.value,
            delivery_channel=reminder.delivery_channel.value,
            status=reminder.status.value,
            snooze_count=reminder.snooze_count,
            local_notification_id=reminder.local_notification_id,
            local_registration_status=reminder.local_registration_status.value,
            failed_reason=reminder.failed_reason,
            fallback_status=reminder.fallback_status.value,
            fallback_after_seconds=reminder.fallback_after_seconds,
            fallback_requested_at=reminder.fallback_requested_at,
            version=reminder.version,
        )


class ReminderCreateRequest(BaseModel):
    """Create a reminder bound to an existing item."""

    item_id: str
    trigger_type: str
    trigger_at: datetime | None = None
    priority: str = "normal"


class ReminderCreateResponse(BaseModel):
    """Created reminder response."""

    reminder: ReminderResponse
    events: list[EventResponse]


class ReminderActionRequest(BaseModel):
    """Client reminder action callback."""

    action: str
    failed_reason: str | None = None
    local_notification_id: str | None = None
    snooze_minutes: int = 10
    fallback_after_seconds: int = 300


class ReminderActionResponse(BaseModel):
    """Reminder action response with emitted events."""

    reminder: ReminderResponse
    events: list[EventResponse]


class EventListResponse(BaseModel):
    """Cursor-based event list."""

    next_cursor: int
    events: list[EventResponse]


class AgendaResponse(BaseModel):
    """Single-panel agenda projection."""

    items: list[ItemResponse] = Field(default_factory=list)
    reminders: list[ReminderResponse] = Field(default_factory=list)


class RepeatRuleResponse(BaseModel):
    """Skeleton repeat rule response."""

    id: str
    pattern: str
    weekdays: list[int]
    time_of_day: str | None
    series_status: str

    @classmethod
    def from_domain(cls, repeat_rule: RepeatRule) -> RepeatRuleResponse:
        """从领域对象构造响应对象。"""
        return cls(
            id=repeat_rule.id,
            pattern=repeat_rule.pattern,
            weekdays=repeat_rule.weekdays,
            time_of_day=repeat_rule.time_of_day,
            series_status=repeat_rule.series_status,
        )


class RepeatRuleCreateRequest(BaseModel):
    """Create a repeat rule skeleton record."""

    pattern: RepeatPatternValue
    weekdays: list[Weekday] = Field(default_factory=list)
    time_of_day: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    series_status: RepeatSeriesStatusValue = "active"


class RepeatRuleCreateResponse(BaseModel):
    """Created repeat rule response."""

    repeat_rule: RepeatRuleResponse


class PermissionDegradeRequest(BaseModel):
    """Request a permission degradation path."""

    permission: str
    reason: str
    title: str = Field(min_length=1)
    place_text: str | None = None


class PermissionDegradeResponse(BaseModel):
    """Permission degradation response."""

    item: ItemResponse
    events: list[EventResponse]
