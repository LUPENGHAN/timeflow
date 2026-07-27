"""P0 application service: command intake, confirmation gate and event output."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from timeapp.application.parser import MockCommandParser
from timeapp.application.reference_resolver import ReferenceResolver
from timeapp.application.store import InMemoryStore
from timeapp.capabilities.calendar.handler import CalendarCapability
from timeapp.capabilities.reminder.handler import ReminderCapability
from timeapp.capabilities.todo.handler import TodoCapability
from timeapp.domain.enums import (
    CommandAction,
    DomainEventType,
    ItemStatus,
    ItemType,
    VoiceCommandStatus,
    WriteRequestStatus,
)
from timeapp.domain.errors import ErrorCode
from timeapp.domain.models import Command, DomainEvent, Identity, Item, VoiceCommand, WriteRequest


class ApplicationError(RuntimeError):
    """Application-layer error with a stable client-facing code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class VoiceCommandResult:
    """Result returned after voice command intake."""

    voice_command: VoiceCommand
    command: Command
    write_request: WriteRequest | None
    events: list[DomainEvent]
    clarification: str | None = None
    candidates: list[Item] = field(default_factory=list)


@dataclass(slots=True)
class ConfirmationResult:
    """Result returned after a user confirms or rejects a write request."""

    write_request: WriteRequest
    events: list[DomainEvent]


class TimeflowApplication:
    """Explicit application orchestration shared by HTTP and WS entrypoints."""

    def __init__(self, store: InMemoryStore | None = None) -> None:
        self.store = store or InMemoryStore()
        self.parser = MockCommandParser()
        self.reference_resolver = ReferenceResolver()
        self.calendar = CalendarCapability()
        self.todo = TodoCapability()
        self.reminder = ReminderCapability()

    def submit_voice_command(self, transcript: str, identity: Identity) -> VoiceCommandResult:
        """Accept transcript, parse command and create a write request if needed."""

        now = datetime.now(UTC)
        command = self.parser.parse(transcript, identity)
        voice_command = VoiceCommand(
            id=str(uuid4()),
            identity=identity,
            transcript=transcript,
            status=VoiceCommandStatus.PARSED,
            command_id=command.id,
            created_at=now,
            updated_at=now,
        )
        self.store.add_voice_command(voice_command)

        status_event = self._event(
            DomainEventType.COMMAND_STATUS_CHANGED,
            "voice_command",
            voice_command.id,
            {"status": voice_command.status.value, "command_id": command.id},
        )
        events = [status_event]

        if command.action == CommandAction.QUERY:
            self.store.add_events(events)
            return VoiceCommandResult(voice_command, command, None, events)

        candidates: list[Item] = []
        if command.action in {CommandAction.UPDATE, CommandAction.DELETE, CommandAction.COMPLETE}:
            candidates = self.reference_resolver.resolve_item_candidates(command, self.store)
            if not candidates:
                voice_command.status = VoiceCommandStatus.NEEDS_CLARIFICATION
                voice_command.updated_at = datetime.now(UTC)
                events.append(
                    self._event(
                        DomainEventType.COMMAND_STATUS_CHANGED,
                        "voice_command",
                        voice_command.id,
                        {
                            "status": voice_command.status.value,
                            "command_id": command.id,
                        },
                    )
                )
                self.store.add_events(events)
                return VoiceCommandResult(
                    voice_command,
                    command,
                    None,
                    events,
                    clarification="没找到要修改的事项，请再说清楚一点。",
                    candidates=[],
                )
            self.store.add_events(events)
            return VoiceCommandResult(
                voice_command,
                command,
                None,
                events,
                clarification="找到候选事项，请先选择要修改的对象。",
                candidates=candidates,
            )

        candidate_payload = self._candidate_payload(command, candidates)
        write_request = WriteRequest(
            id=str(uuid4()),
            identity=identity,
            source_command_id=command.id,
            command=command,
            candidate_payload=candidate_payload,
            payload_hash=self._payload_hash(candidate_payload),
            expires_at=now + timedelta(minutes=10),
            idempotency_key=f"{identity.user_id}:{command.id}",
            created_at=now,
            updated_at=now,
        )
        self.store.add_write_request(write_request)
        events.append(
            self._event(
                DomainEventType.WRITE_REQUEST_CREATED,
                "write_request",
                write_request.id,
                {
                    "status": write_request.status.value,
                    "candidate_payload": write_request.candidate_payload,
                },
            )
        )
        self.store.add_events(events)
        return VoiceCommandResult(voice_command, command, write_request, events)

    def list_pending_write_requests(self, identity: Identity) -> list[WriteRequest]:
        """List pending writes that still require user confirmation."""

        return self.store.list_pending_write_requests(identity.user_id)

    def confirm_write_request(
        self, write_request_id: str, identity: Identity
    ) -> ConfirmationResult:
        """Apply a pending write request through active capability handlers."""

        write_request = self._load_pending_request(write_request_id, identity)
        events = self._apply_write_request(write_request)
        write_request.status = WriteRequestStatus.APPLIED
        write_request.updated_at = datetime.now(UTC)
        events.append(
            self._event(
                DomainEventType.WRITE_REQUEST_APPLIED,
                "write_request",
                write_request.id,
                {"status": write_request.status.value},
            )
        )
        self.store.add_events(events)
        return ConfirmationResult(write_request, events)

    def reject_write_request(self, write_request_id: str, identity: Identity) -> ConfirmationResult:
        """Reject a pending write request without touching business facts."""

        write_request = self._load_pending_request(write_request_id, identity)
        write_request.status = WriteRequestStatus.REJECTED
        write_request.updated_at = datetime.now(UTC)
        events = [
            self._event(
                DomainEventType.WRITE_REQUEST_REJECTED,
                "write_request",
                write_request.id,
                {"status": write_request.status.value},
            )
        ]
        self.store.add_events(events)
        return ConfirmationResult(write_request, events)

    def list_items(self, identity: Identity) -> list[Item]:
        """List user's calendar/todo items."""

        return self.store.list_items(identity.user_id)

    def create_item(
        self,
        identity: Identity,
        item_type: ItemType,
        title: str,
        description: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        due_at: datetime | None = None,
        place_text: str | None = None,
    ) -> tuple[Item, list[DomainEvent]]:
        """Create a manual item without a confirmation gate."""

        now = datetime.now(UTC)
        item = Item(
            id=str(uuid4()),
            user_id=identity.user_id,
            item_type=item_type,
            title=title,
            description=description,
            status=ItemStatus.ACTIVE,
            start_at=start_at,
            end_at=end_at,
            due_at=due_at,
            place_text=place_text,
            created_at=now,
            updated_at=now,
        )
        self.store.add_item(item)
        event = self._event(
            DomainEventType.ITEM_CREATED,
            "item",
            item.id,
            {"item": self._item_payload(item)},
        )
        self.store.add_events([event])
        return item, [event]

    def list_events(self, after_cursor: int = 0) -> list[DomainEvent]:
        """List domain events after a cursor."""

        return self.store.list_events_after(after_cursor)

    def _load_pending_request(self, write_request_id: str, identity: Identity) -> WriteRequest:
        write_request = self.store.get_write_request(write_request_id)
        if write_request is None or write_request.identity.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.WRITE_REQUEST_NOT_FOUND,
                f"Write request {write_request_id} was not found.",
            )
        if write_request.status != WriteRequestStatus.PENDING:
            raise ApplicationError(
                ErrorCode.WRITE_REQUEST_NOT_PENDING,
                f"Write request {write_request_id} is not pending.",
            )
        return write_request

    def _candidate_payload(self, command: Command, candidates: list[Item] | None = None) -> dict[str, Any]:
        operation = str(command.payload.get("operation", ""))
        if not operation:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Command operation is missing.",
            )

        payload: dict[str, Any] = {
            "operation": operation,
            "source_text": command.payload.get("source_text"),
            "item": {
                "title": command.title,
                "description": command.description,
                "start_at": command.start_at.isoformat() if command.start_at else None,
                "end_at": command.end_at.isoformat() if command.end_at else None,
                "due_at": command.due_at.isoformat() if command.due_at else None,
                "priority": command.priority.value,
            },
        }
        if command.action in {CommandAction.UPDATE, CommandAction.DELETE, CommandAction.COMPLETE}:
            payload["operations"] = [
                {
                    "op": operation,
                    "target_id": candidate.id,
                    "target_title": candidate.title,
                    "changes": {
                        "title": command.title,
                        "start_at": command.start_at.isoformat() if command.start_at else None,
                        "end_at": command.end_at.isoformat() if command.end_at else None,
                        "due_at": command.due_at.isoformat() if command.due_at else None,
                    },
                }
                for candidate in candidates or []
            ]
            payload["candidates"] = [self._item_payload(candidate) for candidate in candidates or []]
        if "reminder" in command.payload:
            payload["reminders"] = [command.payload["reminder"]]
        return payload

    def _apply_write_request(self, write_request: WriteRequest) -> list[DomainEvent]:
        operation = str(write_request.candidate_payload.get("operation", ""))
        events: list[DomainEvent] = []

        if operation == "create_calendar_event":
            events.extend(self.calendar.apply(write_request, self.store))
            return events

        if operation == "create_todo":
            events.extend(self.todo.apply(write_request, self.store))
            return events

        if operation == "create_todo_with_reminder":
            todo_events = self.todo.apply(write_request, self.store)
            events.extend(todo_events)
            item_id = self._last_created_item_id(todo_events)
            events.extend(self.reminder.apply(write_request, self.store, item_id))
            return events

        raise ApplicationError(
            ErrorCode.CAPABILITY_NOT_ACTIVE,
            f"Operation {operation} is not active.",
        )

    def _last_created_item_id(self, events: list[DomainEvent]) -> str:
        for event in reversed(events):
            if event.event_type == DomainEventType.ITEM_CREATED:
                return str(event.payload["item"]["id"])
        raise ApplicationError(ErrorCode.MISSING_REQUIRED_FIELD, "No item was created.")

    def _event(
        self,
        event_type: DomainEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> DomainEvent:
        return DomainEvent(
            id=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            version=len(self.store.events) + 1,
            occurred_at=datetime.now(UTC),
            payload=payload,
        )

    def _payload_hash(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _item_payload(self, item: Item) -> dict[str, Any]:
        return {
            "id": item.id,
            "type": item.item_type.value,
            "title": item.title,
            "description": item.description,
            "start_at": item.start_at.isoformat() if item.start_at else None,
            "end_at": item.end_at.isoformat() if item.end_at else None,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "place_text": item.place_text,
            "status": item.status.value,
            "version": item.version,
        }
