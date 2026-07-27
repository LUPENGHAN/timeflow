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
from timeapp.application.store import InMemoryStore, SqlAlchemyStore
from timeapp.capabilities.calendar.handler import CalendarCapability
from timeapp.capabilities.reminder.handler import ReminderCapability
from timeapp.capabilities.todo.handler import TodoCapability
from timeapp.domain.enums import (
    CommandAction,
    CommandEntity,
    DomainEventType,
    FallbackStatus,
    ItemStatus,
    ItemType,
    NotificationRegistrationStatus,
    ReminderPriority,
    ReminderStatus,
    ReminderTriggerType,
    VoiceCommandStatus,
    WriteRequestStatus,
)
from timeapp.domain.errors import ErrorCode
from timeapp.domain.models import (
    Command,
    DomainEvent,
    Identity,
    Item,
    Place,
    Reminder,
    RepeatRule,
    VoiceCommand,
    WriteRequest,
)


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

    def __init__(self, store: InMemoryStore | SqlAlchemyStore | None = None) -> None:
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
            candidates = self._query_items(command)
            self.store.add_events(events)
            return VoiceCommandResult(
                voice_command,
                command,
                None,
                events,
                candidates=candidates,
            )

        candidates: list[Item] = []
        if command.action in {CommandAction.UPDATE, CommandAction.DELETE, CommandAction.COMPLETE}:
            candidates = self.reference_resolver.resolve_item_candidates(command, self.store)
            if not candidates:
                voice_command.status = VoiceCommandStatus.NEEDS_CLARIFICATION
                voice_command.updated_at = datetime.now(UTC)
                self.store.update_voice_command(voice_command)
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

            if len(candidates) > 1:
                voice_command.status = VoiceCommandStatus.NEEDS_CLARIFICATION
                voice_command.updated_at = datetime.now(UTC)
                self.store.update_voice_command(voice_command)
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
                return VoiceCommandResult(
                    voice_command,
                    command,
                    write_request,
                    events,
                    clarification="找到多个候选事项，请先选择要修改的对象。",
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

        pending_requests = self.store.list_pending_write_requests(identity.user_id)
        active_requests: list[WriteRequest] = []
        now = datetime.now(UTC)
        for write_request in pending_requests:
            if write_request.expires_at <= now:
                write_request.status = WriteRequestStatus.EXPIRED
                write_request.updated_at = now
                self.store.update_write_request(write_request)
                continue
            active_requests.append(write_request)
        return active_requests

    def get_write_request(self, write_request_id: str, identity: Identity) -> WriteRequest:
        """Return one write request owned by the current user."""

        write_request = self.store.get_write_request(write_request_id)
        if write_request is None or write_request.identity.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.WRITE_REQUEST_NOT_FOUND,
                f"Write request {write_request_id} was not found.",
            )
        if (
            write_request.status == WriteRequestStatus.PENDING
            and write_request.expires_at <= datetime.now(UTC)
        ):
            write_request.status = WriteRequestStatus.EXPIRED
            write_request.updated_at = datetime.now(UTC)
            self.store.update_write_request(write_request)
        return write_request

    def confirm_write_request(
        self, write_request_id: str, identity: Identity
    ) -> ConfirmationResult:
        """Apply a pending write request through active capability handlers."""

        write_request = self._load_pending_request(write_request_id, identity)
        events = self._apply_write_request(write_request)
        write_request.status = WriteRequestStatus.APPLIED
        write_request.updated_at = datetime.now(UTC)
        self.store.update_write_request(write_request)
        applied_event = self._event(
            DomainEventType.WRITE_REQUEST_APPLIED,
            "write_request",
            write_request.id,
            {"status": write_request.status.value},
        )
        operation = str(write_request.candidate_payload.get("operation", ""))
        if operation in {
            "update_item",
            "complete_item",
            "cancel_complete_item",
            "delete_item",
            "create_reminder",
        }:
            self.store.add_events([applied_event])
        else:
            self.store.add_events([*events, applied_event])
        return ConfirmationResult(write_request, [*events, applied_event])

    def reject_write_request(self, write_request_id: str, identity: Identity) -> ConfirmationResult:
        """Reject a pending write request without touching business facts."""

        write_request = self._load_pending_request(write_request_id, identity)
        write_request.status = WriteRequestStatus.REJECTED
        write_request.updated_at = datetime.now(UTC)
        self.store.update_write_request(write_request)
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

    def update_write_request(
        self,
        write_request_id: str,
        identity: Identity,
        candidate_payload: dict[str, Any],
    ) -> ConfirmationResult:
        """Edit a pending write request without applying business facts."""

        write_request = self._load_pending_request(write_request_id, identity)
        write_request.candidate_payload = candidate_payload
        write_request.payload_hash = self._payload_hash(candidate_payload)
        write_request.updated_at = datetime.now(UTC)
        self.store.update_write_request(write_request)
        events = [
            self._event(
                DomainEventType.WRITE_REQUEST_UPDATED,
                "write_request",
                write_request.id,
                {
                    "status": write_request.status.value,
                    "candidate_payload": write_request.candidate_payload,
                    "payload_hash": write_request.payload_hash,
                },
            )
        ]
        self.store.add_events(events)
        return ConfirmationResult(write_request, events)

    def list_items(self, identity: Identity) -> list[Item]:
        """List user's calendar/todo items."""

        return self.store.list_items(identity.user_id)

    def _query_items(self, command: Command) -> list[Item]:
        """Return items matching a read-only voice query time window."""

        start = command.time_range_start
        end = command.time_range_end
        reminders_by_item: dict[str, list[Reminder]] = {}
        for reminder in self.store.list_reminders(command.identity.user_id):
            reminders_by_item.setdefault(reminder.item_id, []).append(reminder)

        results: list[Item] = []
        for item in self.store.list_items(command.identity.user_id):
            if item.status == ItemStatus.DELETED:
                continue
            anchor = item.start_at or item.due_at
            if anchor is None:
                anchor = next(
                    (
                        reminder.trigger_at
                        for reminder in reminders_by_item.get(item.id, [])
                        if reminder.trigger_at is not None
                    ),
                    None,
                )
            if anchor is None:
                if item.item_type == ItemType.TODO:
                    results.append(item)
                continue
            if (start is None or anchor >= start) and (end is None or anchor < end):
                results.append(item)

        return sorted(results, key=self._item_query_sort_key)

    def _item_query_sort_key(self, item: Item) -> tuple[int, datetime, str]:
        anchor = item.start_at or item.due_at
        if anchor is None:
            return (1, item.updated_at, item.title)
        return (0, anchor, item.title)

    def list_places(self, identity: Identity) -> list[Place]:
        """List skeleton places for a user."""

        return self.store.list_places(identity.user_id)

    def list_repeat_rules(self, identity: Identity) -> list[RepeatRule]:
        """List repeat rules for a user."""

        return self.store.list_repeat_rules(identity.user_id)

    def list_reminders(self, identity: Identity) -> list[Reminder]:
        """List reminders for a user."""

        return self.store.list_reminders(identity.user_id)

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

    def create_place(
        self,
        identity: Identity,
        label: str,
        place_type: str,
        radius_meters: int = 100,
        description: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        accuracy_meters: int | None = None,
    ) -> Place:
        """Create a lightweight place skeleton record."""

        now = datetime.now(UTC)
        place = Place(
            id=str(uuid4()),
            user_id=identity.user_id,
            label=label,
            place_type=place_type,
            radius_meters=radius_meters,
            description=description,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy_meters,
            created_at=now,
            updated_at=now,
        )
        self.store.add_place(place)
        return place

    def update_place(
        self,
        identity: Identity,
        place_id: str,
        label: str | None = None,
        place_type: str | None = None,
        radius_meters: int | None = None,
        description: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        accuracy_meters: int | None = None,
    ) -> Place:
        """Update an existing place owned by the current user."""

        place = self.store.get_place(place_id)
        if place is None or place.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.PLACE_NOT_FOUND,
                f"Place {place_id} was not found.",
            )
        if label is not None:
            place.label = label
        if place_type is not None:
            place.place_type = place_type
        if radius_meters is not None:
            place.radius_meters = radius_meters
        if description is not None:
            place.description = description
        if latitude is not None:
            place.latitude = latitude
        if longitude is not None:
            place.longitude = longitude
        if accuracy_meters is not None:
            place.accuracy_meters = accuracy_meters
        place.updated_at = datetime.now(UTC)
        self.store.update_place(place)
        return place

    def delete_place(self, identity: Identity, place_id: str) -> Place:
        """Delete an existing place owned by the current user."""

        place = self.store.get_place(place_id)
        if place is None or place.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.PLACE_NOT_FOUND,
                f"Place {place_id} was not found.",
            )
        self.store.delete_place(place.id)
        return place

    def create_repeat_rule(
        self,
        identity: Identity,
        pattern: str,
        weekdays: list[int] | None = None,
        time_of_day: str | None = None,
        series_status: str = "active",
    ) -> RepeatRule:
        """Create a lightweight repeat-rule skeleton record."""

        now = datetime.now(UTC)
        repeat_rule = RepeatRule(
            id=str(uuid4()),
            user_id=identity.user_id,
            pattern=pattern,
            weekdays=weekdays or [],
            time_of_day=time_of_day,
            series_status=series_status,
            created_at=now,
            updated_at=now,
        )
        self.store.add_repeat_rule(repeat_rule)
        return repeat_rule

    def create_reminder(
        self,
        identity: Identity,
        item_id: str,
        trigger_type: ReminderTriggerType,
        trigger_at: datetime | None = None,
        place_id: str | None = None,
        priority: ReminderPriority = ReminderPriority.NORMAL,
    ) -> tuple[Reminder, list[DomainEvent]]:
        """Create a reminder bound to an existing user item."""

        item = self.store.get_item(item_id)
        if item is None or item.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.ITEM_NOT_FOUND,
                f"Item {item_id} was not found.",
            )
        if trigger_type == ReminderTriggerType.TIME and trigger_at is None:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Time reminders require trigger_at.",
            )
        if trigger_type != ReminderTriggerType.TIME and place_id is None:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Place reminders require place_id.",
            )

        now = datetime.now(UTC)
        reminder = Reminder(
            id=str(uuid4()),
            user_id=identity.user_id,
            item_id=item.id,
            trigger_type=trigger_type,
            trigger_at=trigger_at,
            place_id=place_id,
            priority=priority,
            status=ReminderStatus.PENDING
            if trigger_type == ReminderTriggerType.TIME
            else ReminderStatus.ARMED,
            created_at=now,
            updated_at=now,
        )
        self.store.add_reminder(reminder)
        event = self._event(
            DomainEventType.WRITE_REQUEST_UPDATED
            if trigger_type == ReminderTriggerType.TIME
            else DomainEventType.REMINDER_ARMED,
            "reminder",
            reminder.id,
            {"reminder": self._reminder_payload(reminder)},
        )
        self.store.add_events([event])
        return reminder, [event]

    def degrade_permission(
        self,
        identity: Identity,
        permission: str,
        reason: str,
        title: str,
        place_text: str | None = None,
    ) -> tuple[Item, list[DomainEvent]]:
        """Apply a P0 permission degradation path."""

        if permission != "location":
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                f"{permission} permission is denied.",
            )
        item, item_events = self.create_item(
            identity=identity,
            item_type=ItemType.TODO,
            title=title,
            place_text=place_text,
        )
        degraded_event = self._event(
            DomainEventType.PERMISSION_DEGRADED,
            "permission",
            permission,
            {
                "permission": permission,
                "reason": reason,
                "degraded_to": "todo_with_text_place",
                "item_id": item.id,
                "place_text": place_text,
            },
        )
        self.store.add_events([degraded_event])
        return item, [*item_events, degraded_event]

    def create_write_request(
        self,
        identity: Identity,
        source_command_id: str,
        candidate_payload: dict[str, Any],
    ) -> tuple[WriteRequest, list[DomainEvent]]:
        """Create a pending write request from a confirmed candidate payload."""

        now = datetime.now(UTC)
        command = self._command_from_candidate_payload(
            identity,
            source_command_id,
            candidate_payload,
        )
        write_request = WriteRequest(
            id=str(uuid4()),
            identity=identity,
            source_command_id=source_command_id,
            command=command,
            candidate_payload=candidate_payload,
            payload_hash=self._payload_hash(candidate_payload),
            expires_at=now + timedelta(minutes=10),
            idempotency_key=(
                f"{identity.user_id}:{source_command_id}:{len(self.store.write_requests) + 1}"
            ),
            created_at=now,
            updated_at=now,
        )
        self.store.add_write_request(write_request)
        event = self._event(
            DomainEventType.WRITE_REQUEST_CREATED,
            "write_request",
            write_request.id,
            {
                "status": write_request.status.value,
                "candidate_payload": write_request.candidate_payload,
            },
        )
        self.store.add_events([event])
        return write_request, [event]

    def update_item(
        self,
        identity: Identity,
        item_id: str,
        title: str | None = None,
        description: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        due_at: datetime | None = None,
        place_text: str | None = None,
        status: ItemStatus | None = None,
    ) -> tuple[Item, list[DomainEvent]]:
        """Update an existing item and emit a domain event."""

        changes: dict[str, Any] = {}
        if title is not None:
            changes["title"] = title
        if description is not None:
            changes["description"] = description
        if start_at is not None:
            changes["start_at"] = start_at
        if end_at is not None:
            changes["end_at"] = end_at
        if due_at is not None:
            changes["due_at"] = due_at
        if place_text is not None:
            changes["place_text"] = place_text
        if status is not None:
            changes["status"] = status
        return self.update_item_fields(identity, item_id, changes)

    def update_item_fields(
        self,
        identity: Identity,
        item_id: str,
        changes: dict[str, Any],
    ) -> tuple[Item, list[DomainEvent]]:
        """Update only explicitly provided item fields and emit a domain event."""

        item = self.store.get_item(item_id)
        if item is None or item.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.ITEM_NOT_FOUND,
                f"Item {item_id} was not found.",
            )

        if "title" in changes:
            title = self._optional_str(changes.get("title"))
            if title is None:
                raise ApplicationError(
                    ErrorCode.MISSING_REQUIRED_FIELD,
                    "Item title cannot be empty.",
                )
            item.title = title
        if "description" in changes:
            item.description = self._nullable_str(changes.get("description"))
        if "start_at" in changes:
            item.start_at = self._nullable_datetime(changes.get("start_at"))
        if "end_at" in changes:
            item.end_at = self._nullable_datetime(changes.get("end_at"))
        if "due_at" in changes:
            item.due_at = self._nullable_datetime(changes.get("due_at"))
        if "place_text" in changes:
            item.place_text = self._nullable_str(changes.get("place_text"))
        if "status" in changes:
            status_value = changes.get("status")
            item.status = (
                status_value
                if isinstance(status_value, ItemStatus)
                else ItemStatus(str(status_value))
            )
        item.version += 1
        item.updated_at = datetime.now(UTC)
        self.store.update_item(item)
        event = self._event(
            DomainEventType.ITEM_UPDATED,
            "item",
            item.id,
            {"item": self._item_payload(item)},
        )
        self.store.add_events([event])
        return item, [event]

    def delete_item(self, identity: Identity, item_id: str) -> tuple[Item, list[DomainEvent]]:
        """Mark an item as deleted."""

        return self.update_item(identity, item_id, status=ItemStatus.DELETED)

    def complete_item(self, identity: Identity, item_id: str) -> tuple[Item, list[DomainEvent]]:
        """Mark an item as completed."""

        return self.update_item(identity, item_id, status=ItemStatus.COMPLETED)

    def apply_reminder_action(
        self,
        identity: Identity,
        reminder_id: str,
        action: str,
        failed_reason: str | None = None,
        local_notification_id: str | None = None,
        snooze_minutes: int = 10,
        fallback_after_seconds: int = 300,
    ) -> tuple[Reminder, list[DomainEvent]]:
        """Apply a client reminder action and emit sync/fallback events."""

        reminder = self.store.get_reminder(reminder_id)
        if reminder is None or reminder.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.REMINDER_NOT_FOUND,
                f"Reminder {reminder_id} was not found.",
            )

        now = datetime.now(UTC)
        event_type = DomainEventType.WRITE_REQUEST_UPDATED

        if action == "registered":
            reminder.local_registration_status = NotificationRegistrationStatus.REGISTERED
            reminder.local_notification_id = local_notification_id
        elif action == "delivered":
            reminder.status = ReminderStatus.DELIVERED
            reminder.last_triggered_at = now
            event_type = DomainEventType.REMINDER_DELIVERED
        elif action == "dismiss":
            reminder.status = ReminderStatus.DISMISSED
            event_type = DomainEventType.REMINDER_DISMISSED
        elif action == "snooze":
            reminder.status = ReminderStatus.SNOOZED
            reminder.snooze_count += 1
            reminder.trigger_at = now + timedelta(minutes=snooze_minutes)
            event_type = DomainEventType.REMINDER_SNOOZED
        elif action == "cancel":
            reminder.status = ReminderStatus.CANCELLED
            reminder.cancelled_at = now
            event_type = DomainEventType.REMINDER_CANCELLED
        elif action in {"failed", "registration_failed", "local_unavailable"}:
            reminder.status = ReminderStatus.FAILED
            reminder.failed_reason = failed_reason or action
            reminder.local_registration_status = (
                NotificationRegistrationStatus.UNAVAILABLE
                if action == "local_unavailable"
                else NotificationRegistrationStatus.FAILED
            )
            reminder.fallback_status = FallbackStatus.REQUESTED
            reminder.fallback_after_seconds = fallback_after_seconds
            reminder.fallback_requested_at = now
            event_type = (
                DomainEventType.NOTIFICATION_REGISTRATION_FAILED
                if action == "registration_failed"
                else DomainEventType.REMINDER_FAILED
            )
        else:
            raise ApplicationError(
                ErrorCode.UNKNOWN_ACTION,
                f"Unsupported reminder action {action}.",
            )

        reminder.version += 1
        reminder.updated_at = now
        self.store.update_reminder(reminder)
        events = [
            self._event(
                event_type,
                "reminder",
                reminder.id,
                {"reminder": self._reminder_payload(reminder)},
            )
        ]
        if reminder.fallback_status == FallbackStatus.REQUESTED:
            events.append(
                self._event(
                    DomainEventType.NOTIFICATION_FALLBACK_REQUESTED,
                    "reminder",
                    reminder.id,
                    {
                        "reminder_id": reminder.id,
                        "fallback_after_seconds": reminder.fallback_after_seconds,
                        "failed_reason": reminder.failed_reason,
                    },
                )
            )
        self.store.add_events(events)
        return reminder, events

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
        if write_request.expires_at <= datetime.now(UTC):
            write_request.status = WriteRequestStatus.EXPIRED
            write_request.updated_at = datetime.now(UTC)
            self.store.update_write_request(write_request)
            raise ApplicationError(
                ErrorCode.WRITE_REQUEST_EXPIRED,
                f"Write request {write_request_id} has expired.",
            )
        return write_request

    def _candidate_payload(
        self,
        command: Command,
        candidates: list[Item] | None = None,
    ) -> dict[str, Any]:
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
            payload["candidates"] = [
                self._item_payload(candidate) for candidate in candidates or []
            ]
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

        if operation == "create_reminder":
            return self._apply_reminder_operations(write_request)

        if operation == "update_item":
            return self._apply_item_operations(write_request, "update")

        if operation == "complete_item":
            return self._apply_item_operations(write_request, "complete")

        if operation == "cancel_complete_item":
            return self._apply_item_operations(write_request, "activate")

        if operation == "delete_item":
            return self._apply_item_operations(write_request, "delete")

        raise ApplicationError(
            ErrorCode.CAPABILITY_NOT_ACTIVE,
            f"Operation {operation} is not active.",
        )

    def _apply_item_operations(self, write_request: WriteRequest, mode: str) -> list[DomainEvent]:
        operations = write_request.candidate_payload.get("operations", [])
        if not isinstance(operations, list) or not operations:
            target_id = self._optional_str(write_request.candidate_payload.get("target_id"))
            if target_id is None:
                raise ApplicationError(
                    ErrorCode.MISSING_REQUIRED_FIELD,
                    "Item operations are missing.",
                )
            operations = [
                {
                    "target_id": target_id,
                    "changes": write_request.candidate_payload.get("item", {}),
                }
            ]
        elif len(operations) > 1:
            raise ApplicationError(
                ErrorCode.CLARIFICATION_REQUIRED,
                "Please choose one candidate item before confirming the write request.",
            )

        events: list[DomainEvent] = []
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            target_id = self._optional_str(operation.get("target_id"))
            if target_id is None:
                continue
            changes = operation.get("changes", {})
            if not isinstance(changes, dict):
                changes = {}
            if mode == "update":
                _, item_events = self.update_item_fields(
                    write_request.identity,
                    target_id,
                    changes,
                )
            elif mode == "complete":
                _, item_events = self.complete_item(write_request.identity, target_id)
            elif mode == "activate":
                _, item_events = self.update_item(
                    write_request.identity,
                    target_id,
                    status=ItemStatus.ACTIVE,
                )
            else:
                _, item_events = self.delete_item(write_request.identity, target_id)
            events.extend(item_events)

        return events

    def _apply_reminder_operations(self, write_request: WriteRequest) -> list[DomainEvent]:
        target_id = self._optional_str(write_request.candidate_payload.get("target_id"))
        if target_id is None:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Reminder target item is missing.",
            )

        reminder_payloads = write_request.candidate_payload.get("reminders", [])
        if not isinstance(reminder_payloads, list) or not reminder_payloads:
            reminder_payloads = [write_request.candidate_payload.get("reminder", {})]

        events: list[DomainEvent] = []
        for payload in reminder_payloads:
            if not isinstance(payload, dict):
                continue
            trigger_type = ReminderTriggerType(str(payload.get("trigger_type", "time")))
            priority = ReminderPriority(str(payload.get("priority", "normal")))
            _, reminder_events = self.create_reminder(
                identity=write_request.identity,
                item_id=target_id,
                trigger_type=trigger_type,
                trigger_at=self._optional_datetime(payload.get("trigger_at")),
                place_id=self._optional_str(payload.get("place_id"))
                or self._optional_str(payload.get("place_ref")),
                priority=priority,
            )
            events.extend(reminder_events)

        return events

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

    def _command_from_candidate_payload(
        self,
        identity: Identity,
        source_command_id: str,
        candidate_payload: dict[str, Any],
    ) -> Command:
        operation = str(candidate_payload.get("operation", ""))
        item_payload = candidate_payload.get("item", {})
        if not isinstance(item_payload, dict):
            item_payload = {}
        entity_name = str(item_payload.get("type") or candidate_payload.get("entity") or "todo")
        entity = (
            CommandEntity.CALENDAR_EVENT if entity_name == "calendar_event" else CommandEntity.TODO
        )
        action = (
            CommandAction.UPDATE
            if operation.startswith("update")
            else CommandAction.DELETE
            if operation.startswith("delete")
            else CommandAction.COMPLETE
            if operation.startswith("complete")
            else CommandAction.CREATE
        )
        return Command(
            id=source_command_id,
            identity=identity,
            action=action,
            entity=entity,
            title=str(item_payload.get("title") or candidate_payload.get("title") or ""),
            description=self._optional_str(item_payload.get("description")),
            target_id=self._optional_str(candidate_payload.get("target_id")),
            start_at=self._optional_datetime(item_payload.get("start_at")),
            end_at=self._optional_datetime(item_payload.get("end_at")),
            due_at=self._optional_datetime(item_payload.get("due_at")),
            payload=candidate_payload,
        )

    def _optional_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value)

    def _optional_str(self, value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    def _nullable_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self._optional_datetime(value)

    def _nullable_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

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

    def _reminder_payload(self, reminder: Reminder) -> dict[str, Any]:
        return {
            "id": reminder.id,
            "item_id": reminder.item_id,
            "trigger_type": reminder.trigger_type.value,
            "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
            "place_id": reminder.place_id,
            "priority": reminder.priority.value,
            "delivery_channel": reminder.delivery_channel.value,
            "status": reminder.status.value,
            "snooze_count": reminder.snooze_count,
            "local_notification_id": reminder.local_notification_id,
            "local_registration_status": reminder.local_registration_status.value,
            "failed_reason": reminder.failed_reason,
            "fallback_status": reminder.fallback_status.value,
            "fallback_after_seconds": reminder.fallback_after_seconds,
            "fallback_requested_at": reminder.fallback_requested_at.isoformat()
            if reminder.fallback_requested_at
            else None,
            "version": reminder.version,
        }
