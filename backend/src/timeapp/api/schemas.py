"""Pydantic request and response models for the P0 API skeleton."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from timeapp.domain.models import DomainEvent, Item, Reminder, VoiceCommand, WriteRequest


class VoiceCommandCreateRequest(BaseModel):
    """Create a voice command from a transcript.

    Real ASR can later replace the transcript field with an uploaded audio
    object while preserving the application flow.
    """

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
    """Response after mock ASR/parser intake."""

    voice_command: VoiceCommandResponse
    write_request: WriteRequestResponse | None
    events: list[EventResponse]
    clarification: str | None = None
    candidates: list[ItemResponse] = Field(default_factory=list)


class ConfirmationResponse(BaseModel):
    """Response after confirm/reject actions."""

    write_request: WriteRequestResponse
    events: list[EventResponse]


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
    reminders: list[ReminderResponse] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, item: Item, reminders: list[Reminder] | None = None) -> ItemResponse:
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


class ItemCreateResponse(BaseModel):
    """Created item response."""

    item: ItemResponse
    events: list[EventResponse]


class ReminderResponse(BaseModel):
    """Reminder response bound to an item."""

    id: str
    item_id: str
    trigger_type: str
    trigger_at: datetime | None
    place_id: str | None
    priority: str
    delivery_channel: str
    status: str

    @classmethod
    def from_domain(cls, reminder: Reminder) -> ReminderResponse:
        return cls(
            id=reminder.id,
            item_id=reminder.item_id,
            trigger_type=reminder.trigger_type.value,
            trigger_at=reminder.trigger_at,
            place_id=reminder.place_id,
            priority=reminder.priority.value,
            delivery_channel=reminder.delivery_channel.value,
            status=reminder.status.value,
        )


class EventListResponse(BaseModel):
    """Cursor-based event list."""

    next_cursor: int
    events: list[EventResponse]


class AgendaResponse(BaseModel):
    """Single-panel agenda projection."""

    items: list[ItemResponse] = Field(default_factory=list)
    reminders: list[ReminderResponse] = Field(default_factory=list)
