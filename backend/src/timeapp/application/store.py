"""Storage implementations for the MS1 executable skeleton.

The in-memory store is kept for fast unit tests. The SQLAlchemy-backed store is
used by the API runtime so Swagger calls persist to the configured database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock

from sqlalchemy import select
from sqlalchemy.orm import Session

from timeapp.domain.enums import (
    CommandAction,
    CommandEntity,
    DeliveryChannel,
    DomainEventType,
    FallbackStatus,
    ItemStatus,
    ItemType,
    NotificationRegistrationStatus,
    ReminderPriority,
    ReminderStatus,
    ReminderTriggerType,
    WriteRequestStatus,
)
from timeapp.domain.models import (
    Command,
    DomainEvent,
    Identity,
    Item,
    OutboxMessage,
    Place,
    Reminder,
    RepeatRule,
    VoiceCommand,
    WriteRequest,
)
from timeapp.infrastructure.models import (
    DomainEventRecord,
    ItemRecord,
    OutboxMessageRecord,
    PlaceRecord,
    ReminderRecord,
    ReminderRuleRecord,
    VoiceCommandRecord,
    WriteRequestRecord,
)


@dataclass(slots=True)
class InMemoryStore:
    """Small explicit storage boundary used by tests and local skeleton routes."""

    voice_commands: dict[str, VoiceCommand] = field(default_factory=dict)
    write_requests: dict[str, WriteRequest] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    places: dict[str, Place] = field(default_factory=dict)
    repeat_rules: dict[str, RepeatRule] = field(default_factory=dict)
    reminders: dict[str, Reminder] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    outbox_messages: list[OutboxMessage] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock)

    def add_voice_command(self, voice_command: VoiceCommand) -> None:
        """Persist a voice command audit record."""

        with self._lock:
            self.voice_commands[voice_command.id] = voice_command

    def update_voice_command(self, voice_command: VoiceCommand) -> None:
        """Persist an updated voice command audit record."""

        self.add_voice_command(voice_command)

    def add_write_request(self, write_request: WriteRequest) -> None:
        """Persist a pending write request."""

        with self._lock:
            self.write_requests[write_request.id] = write_request

    def update_write_request(self, write_request: WriteRequest) -> None:
        """Persist an updated write request."""

        self.add_write_request(write_request)

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """Load a write request by id."""

        with self._lock:
            return self.write_requests.get(write_request_id)

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """Return pending write requests for a user."""

        with self._lock:
            return [
                request
                for request in self.write_requests.values()
                if request.identity.user_id == user_id
                and request.status == WriteRequestStatus.PENDING
            ]

    def add_item(self, item: Item) -> None:
        """Persist a calendar or todo item."""

        with self._lock:
            self.items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        """Load an item by id."""

        with self._lock:
            return self.items.get(item_id)

    def update_item(self, item: Item) -> None:
        """Persist an updated item."""

        with self._lock:
            self.items[item.id] = item

    def add_place(self, place: Place) -> None:
        """Persist a place."""

        with self._lock:
            self.places[place.id] = place

    def get_place(self, place_id: str) -> Place | None:
        """Load a place by id."""

        with self._lock:
            return self.places.get(place_id)

    def update_place(self, place: Place) -> None:
        """Persist an updated place."""

        self.add_place(place)

    def delete_place(self, place_id: str) -> None:
        """Delete a place by id."""

        with self._lock:
            self.places.pop(place_id, None)

    def list_places(self, user_id: str) -> list[Place]:
        """Return all visible places for a user."""

        with self._lock:
            return [place for place in self.places.values() if place.user_id == user_id]

    def add_repeat_rule(self, repeat_rule: RepeatRule) -> None:
        """Persist a repeat rule."""

        with self._lock:
            self.repeat_rules[repeat_rule.id] = repeat_rule

    def list_repeat_rules(self, user_id: str) -> list[RepeatRule]:
        """Return repeat rules for a user."""

        with self._lock:
            return [
                repeat_rule
                for repeat_rule in self.repeat_rules.values()
                if repeat_rule.user_id == user_id
            ]

    def add_reminder(self, reminder: Reminder) -> None:
        """Persist a reminder."""

        with self._lock:
            self.reminders[reminder.id] = reminder

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """Load a reminder by id."""

        with self._lock:
            return self.reminders.get(reminder_id)

    def update_reminder(self, reminder: Reminder) -> None:
        """Persist an updated reminder."""

        with self._lock:
            self.reminders[reminder.id] = reminder

    def list_reminders(self, user_id: str) -> list[Reminder]:
        """Return reminders for a user."""

        with self._lock:
            return [reminder for reminder in self.reminders.values() if reminder.user_id == user_id]

    def add_events(self, events: list[DomainEvent]) -> None:
        """Append domain events in order."""

        with self._lock:
            start_version = len(self.events) + 1
            for index, event in enumerate(events):
                event.version = start_version + index
            self.events.extend(events)
            self.outbox_messages.extend(
                OutboxMessage(
                    id=event.id,
                    event_id=event.id,
                    channel="ws",
                    payload=event.payload,
                )
                for event in events
            )

    def list_items(self, user_id: str) -> list[Item]:
        """Return all visible items for a user."""

        with self._lock:
            return [
                item
                for item in self.items.values()
                if item.user_id == user_id and item.status != ItemStatus.DELETED
            ]

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """Return events after a one-based cursor."""

        with self._lock:
            return self.events[cursor:]

    def list_outbox_messages(self) -> list[OutboxMessage]:
        """Return in-memory outbox messages."""

        with self._lock:
            return list(self.outbox_messages)


class SqlAlchemyStore:
    """SQLAlchemy implementation used by the real API runtime."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def events(self) -> list[DomainEvent]:
        """Return all events for compatibility with existing event version logic."""

        return self.list_events_after(0)

    @property
    def write_requests(self) -> dict[str, WriteRequest]:
        """Return all write requests keyed by id for compatibility with legacy code."""

        records = self.session.scalars(select(WriteRequestRecord)).all()
        return {record.id: self._write_request_from_record(record) for record in records}

    @property
    def reminders(self) -> dict[str, Reminder]:
        """Return all reminders keyed by id for compatibility with legacy code."""

        records = self.session.scalars(select(ReminderRecord)).all()
        return {record.id: self._reminder_from_record(record) for record in records}

    def add_voice_command(self, voice_command: VoiceCommand) -> None:
        """Persist a voice command audit record."""

        self.session.add(
            VoiceCommandRecord(
                id=voice_command.id,
                user_id=voice_command.identity.user_id,
                device_id=voice_command.identity.device_id,
                session_id=voice_command.identity.session_id,
                transcript=voice_command.transcript,
                status=voice_command.status.value,
                parsed_command={"command_id": voice_command.command_id},
                error_code=voice_command.error_code,
                created_at=voice_command.created_at,
                updated_at=voice_command.updated_at,
            )
        )
        self.session.commit()

    def update_voice_command(self, voice_command: VoiceCommand) -> None:
        """Persist an updated voice command audit record."""

        record = self.session.get(VoiceCommandRecord, voice_command.id)
        if record is None:
            self.add_voice_command(voice_command)
            return
        record.status = voice_command.status.value
        record.parsed_command = {"command_id": voice_command.command_id}
        record.error_code = voice_command.error_code
        record.updated_at = voice_command.updated_at
        self.session.commit()

    def add_write_request(self, write_request: WriteRequest) -> None:
        """Persist a pending write request."""

        self.session.add(self._write_request_to_record(write_request))
        self.session.commit()

    def update_write_request(self, write_request: WriteRequest) -> None:
        """Persist an updated write request."""

        record = self.session.get(WriteRequestRecord, write_request.id)
        if record is None:
            self.add_write_request(write_request)
            return
        record.candidate_payload = write_request.candidate_payload
        record.payload_hash = write_request.payload_hash
        record.status = write_request.status.value
        record.expires_at = write_request.expires_at
        record.updated_at = write_request.updated_at
        self.session.commit()

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """Load a write request by id."""

        record = self.session.get(WriteRequestRecord, write_request_id)
        return self._write_request_from_record(record) if record is not None else None

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """Return pending write requests for a user."""

        records = self.session.scalars(
            select(WriteRequestRecord)
            .where(
                WriteRequestRecord.user_id == user_id,
                WriteRequestRecord.status == WriteRequestStatus.PENDING.value,
            )
            .order_by(WriteRequestRecord.created_at)
        ).all()
        return [self._write_request_from_record(record) for record in records]

    def add_item(self, item: Item) -> None:
        """Persist a calendar or todo item."""

        self.session.add(self._item_to_record(item))
        self.session.commit()

    def get_item(self, item_id: str) -> Item | None:
        """Load an item by id."""

        record = self.session.get(ItemRecord, item_id)
        return self._item_from_record(record) if record is not None else None

    def update_item(self, item: Item) -> None:
        """Persist an updated item."""

        record = self.session.get(ItemRecord, item.id)
        if record is None:
            self.add_item(item)
            return
        record.item_type = item.item_type.value
        record.title = item.title
        record.description = item.description
        record.status = item.status.value
        record.start_at = item.start_at
        record.end_at = item.end_at
        record.due_at = item.due_at
        record.place_text = item.place_text
        record.timezone = item.timezone
        record.version = item.version
        record.updated_at = item.updated_at
        record.deleted_at = item.updated_at if item.status == ItemStatus.DELETED else None
        self.session.commit()

    def list_items(self, user_id: str) -> list[Item]:
        """Return all visible items for a user."""

        records = self.session.scalars(
            select(ItemRecord)
            .where(
                ItemRecord.user_id == user_id,
                ItemRecord.status != ItemStatus.DELETED.value,
            )
            .order_by(ItemRecord.created_at)
        ).all()
        return [self._item_from_record(record) for record in records]

    def add_place(self, place: Place) -> None:
        """Persist a place."""

        self.session.add(
            PlaceRecord(
                id=place.id,
                user_id=place.user_id,
                label=place.label,
                place_type=place.place_type,
                latitude=place.latitude,
                longitude=place.longitude,
                accuracy_meters=place.accuracy_meters,
                radius_meters=place.radius_meters,
                description=place.description,
                created_at=place.created_at,
                updated_at=place.updated_at,
            )
        )
        self.session.commit()

    def get_place(self, place_id: str) -> Place | None:
        """Load a place by id."""

        record = self.session.get(PlaceRecord, place_id)
        return self._place_from_record(record) if record is not None else None

    def update_place(self, place: Place) -> None:
        """Persist an updated place."""

        record = self.session.get(PlaceRecord, place.id)
        if record is None:
            self.add_place(place)
            return
        record.label = place.label
        record.place_type = place.place_type
        record.latitude = place.latitude
        record.longitude = place.longitude
        record.accuracy_meters = place.accuracy_meters
        record.radius_meters = place.radius_meters
        record.description = place.description
        record.updated_at = place.updated_at
        self.session.commit()

    def delete_place(self, place_id: str) -> None:
        """Delete a place by id."""

        record = self.session.get(PlaceRecord, place_id)
        if record is not None:
            self.session.delete(record)
            self.session.commit()

    def list_places(self, user_id: str) -> list[Place]:
        """Return all visible places for a user."""

        records = self.session.scalars(
            select(PlaceRecord)
            .where(PlaceRecord.user_id == user_id)
            .order_by(PlaceRecord.created_at)
        ).all()
        return [self._place_from_record(record) for record in records]

    def add_repeat_rule(self, repeat_rule: RepeatRule) -> None:
        """Persist a repeat rule using the skeleton reminder_rules table."""

        self.session.add(
            ReminderRuleRecord(
                id=repeat_rule.id,
                user_id=repeat_rule.user_id,
                item_id=None,
                rule_payload={
                    "pattern": repeat_rule.pattern,
                    "weekdays": repeat_rule.weekdays,
                    "time_of_day": repeat_rule.time_of_day,
                },
                status=repeat_rule.series_status,
                created_at=repeat_rule.created_at,
                updated_at=repeat_rule.updated_at,
            )
        )
        self.session.commit()

    def list_repeat_rules(self, user_id: str) -> list[RepeatRule]:
        """Return repeat rules for a user."""

        records = self.session.scalars(
            select(ReminderRuleRecord)
            .where(ReminderRuleRecord.user_id == user_id)
            .order_by(ReminderRuleRecord.created_at)
        ).all()
        return [self._repeat_rule_from_record(record) for record in records]

    def add_reminder(self, reminder: Reminder) -> None:
        """Persist a reminder."""

        self.session.add(self._reminder_to_record(reminder))
        self.session.commit()

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """Load a reminder by id."""

        record = self.session.get(ReminderRecord, reminder_id)
        return self._reminder_from_record(record) if record is not None else None

    def update_reminder(self, reminder: Reminder) -> None:
        """Persist an updated reminder."""

        record = self.session.get(ReminderRecord, reminder.id)
        if record is None:
            self.add_reminder(reminder)
            return
        record.trigger_type = reminder.trigger_type.value
        record.trigger_at = reminder.trigger_at
        record.place_id = reminder.place_id
        record.priority = reminder.priority.value
        record.delivery_channel = reminder.delivery_channel.value
        record.status = reminder.status.value
        record.snooze_count = reminder.snooze_count
        record.last_triggered_at = reminder.last_triggered_at
        record.local_notification_id = reminder.local_notification_id
        record.local_registration_status = reminder.local_registration_status.value
        record.expires_at = reminder.expires_at
        record.failed_reason = reminder.failed_reason
        record.fallback_status = reminder.fallback_status.value
        record.fallback_after_seconds = reminder.fallback_after_seconds
        record.fallback_requested_at = reminder.fallback_requested_at
        record.version = reminder.version
        record.updated_at = reminder.updated_at
        record.cancelled_at = reminder.cancelled_at
        self.session.commit()

    def list_reminders(self, user_id: str) -> list[Reminder]:
        """Return reminders for a user."""

        records = self.session.scalars(
            select(ReminderRecord)
            .where(ReminderRecord.user_id == user_id)
            .order_by(ReminderRecord.created_at)
        ).all()
        return [self._reminder_from_record(record) for record in records]

    def add_events(self, events: list[DomainEvent]) -> None:
        """Append domain events and matching outbox messages."""

        current_max_version = self.session.scalar(select(DomainEventRecord.version).order_by(DomainEventRecord.version.desc()).limit(1))
        start_version = int(current_max_version or 0) + 1
        for event in events:
            event.version = start_version
            self.session.add(
                DomainEventRecord(
                    id=event.id,
                    event_type=event.event_type.value,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    version=event.version,
                    occurred_at=event.occurred_at,
                    payload=event.payload,
                )
            )
            self.session.add(
                OutboxMessageRecord(
                    id=event.id,
                    event_id=event.id,
                    channel="ws",
                    payload=event.payload,
                    status="pending",
                    attempts=0,
                    created_at=event.occurred_at,
                    updated_at=event.occurred_at,
                )
            )
            start_version += 1
        self.session.commit()

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """Return events after a one-based cursor."""

        records = self.session.scalars(
            select(DomainEventRecord)
            .where(DomainEventRecord.version > cursor)
            .order_by(DomainEventRecord.version)
        ).all()
        return [self._event_from_record(record) for record in records]

    def list_outbox_messages(self) -> list[OutboxMessage]:
        """Return outbox messages."""

        records = self.session.scalars(
            select(OutboxMessageRecord).order_by(OutboxMessageRecord.created_at)
        ).all()
        return [self._outbox_from_record(record) for record in records]

    def _write_request_to_record(self, write_request: WriteRequest) -> WriteRequestRecord:
        return WriteRequestRecord(
            id=write_request.id,
            user_id=write_request.identity.user_id,
            source_command_id=write_request.source_command_id,
            action=write_request.command.action.value,
            entity=write_request.command.entity.value,
            target_id=write_request.command.target_id,
            candidate_payload=write_request.candidate_payload,
            payload_hash=write_request.payload_hash,
            idempotency_key=write_request.idempotency_key,
            status=write_request.status.value,
            expires_at=write_request.expires_at,
            created_at=write_request.created_at,
            updated_at=write_request.updated_at,
        )

    def _write_request_from_record(self, record: WriteRequestRecord) -> WriteRequest:
        identity = Identity(user_id=record.user_id)
        item_payload = record.candidate_payload.get("item", {})
        if not isinstance(item_payload, dict):
            item_payload = {}
        command = Command(
            id=record.source_command_id,
            identity=identity,
            action=CommandAction(record.action),
            entity=CommandEntity(record.entity),
            title=self._optional_str(item_payload.get("title")),
            description=self._optional_str(item_payload.get("description")),
            target_id=record.target_id,
            start_at=self._optional_datetime(item_payload.get("start_at")),
            end_at=self._optional_datetime(item_payload.get("end_at")),
            due_at=self._optional_datetime(item_payload.get("due_at")),
            payload=record.candidate_payload,
            created_at=record.created_at,
        )
        return WriteRequest(
            id=record.id,
            identity=identity,
            source_command_id=record.source_command_id,
            command=command,
            candidate_payload=record.candidate_payload,
            payload_hash=record.payload_hash,
            expires_at=record.expires_at,
            idempotency_key=record.idempotency_key,
            status=WriteRequestStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _item_to_record(self, item: Item) -> ItemRecord:
        return ItemRecord(
            id=item.id,
            user_id=item.user_id,
            item_type=item.item_type.value,
            title=item.title,
            description=item.description,
            status=item.status.value,
            start_at=item.start_at,
            end_at=item.end_at,
            due_at=item.due_at,
            place_text=item.place_text,
            timezone=item.timezone,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.updated_at if item.status == ItemStatus.DELETED else None,
        )

    def _item_from_record(self, record: ItemRecord) -> Item:
        return Item(
            id=record.id,
            user_id=record.user_id,
            item_type=ItemType(record.item_type),
            title=record.title,
            description=record.description,
            status=ItemStatus(record.status),
            start_at=record.start_at,
            end_at=record.end_at,
            due_at=record.due_at,
            place_text=record.place_text,
            timezone=record.timezone,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _place_from_record(self, record: PlaceRecord) -> Place:
        return Place(
            id=record.id,
            user_id=record.user_id,
            label=record.label,
            place_type=record.place_type,
            latitude=record.latitude,
            longitude=record.longitude,
            accuracy_meters=record.accuracy_meters,
            radius_meters=record.radius_meters,
            description=record.description,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _repeat_rule_from_record(self, record: ReminderRuleRecord) -> RepeatRule:
        payload = record.rule_payload
        weekdays = payload.get("weekdays", [])
        if not isinstance(weekdays, list):
            weekdays = []
        return RepeatRule(
            id=record.id,
            user_id=record.user_id,
            pattern=str(payload.get("pattern", "daily")),
            weekdays=[int(weekday) for weekday in weekdays],
            time_of_day=self._optional_str(payload.get("time_of_day")),
            series_status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _reminder_to_record(self, reminder: Reminder) -> ReminderRecord:
        return ReminderRecord(
            id=reminder.id,
            user_id=reminder.user_id,
            item_id=reminder.item_id,
            trigger_type=reminder.trigger_type.value,
            trigger_at=reminder.trigger_at,
            place_id=reminder.place_id,
            priority=reminder.priority.value,
            delivery_channel=reminder.delivery_channel.value,
            status=reminder.status.value,
            snooze_count=reminder.snooze_count,
            last_triggered_at=reminder.last_triggered_at,
            local_notification_id=reminder.local_notification_id,
            local_registration_status=reminder.local_registration_status.value,
            expires_at=reminder.expires_at,
            failed_reason=reminder.failed_reason,
            fallback_status=reminder.fallback_status.value,
            fallback_after_seconds=reminder.fallback_after_seconds,
            fallback_requested_at=reminder.fallback_requested_at,
            version=reminder.version,
            created_at=reminder.created_at,
            updated_at=reminder.updated_at,
            cancelled_at=reminder.cancelled_at,
        )

    def _reminder_from_record(self, record: ReminderRecord) -> Reminder:
        return Reminder(
            id=record.id,
            user_id=record.user_id,
            item_id=record.item_id,
            trigger_type=ReminderTriggerType(record.trigger_type),
            trigger_at=record.trigger_at,
            place_id=record.place_id,
            priority=ReminderPriority(record.priority),
            delivery_channel=DeliveryChannel(record.delivery_channel),
            status=ReminderStatus(record.status),
            snooze_count=record.snooze_count,
            last_triggered_at=record.last_triggered_at,
            local_notification_id=record.local_notification_id,
            local_registration_status=NotificationRegistrationStatus(
                record.local_registration_status
            ),
            expires_at=record.expires_at,
            failed_reason=record.failed_reason,
            fallback_status=FallbackStatus(record.fallback_status),
            fallback_after_seconds=record.fallback_after_seconds,
            fallback_requested_at=record.fallback_requested_at,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            cancelled_at=record.cancelled_at,
        )

    def _event_from_record(self, record: DomainEventRecord) -> DomainEvent:
        return DomainEvent(
            id=record.id,
            event_type=DomainEventType(record.event_type),
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            version=record.version,
            occurred_at=record.occurred_at,
            payload=record.payload,
        )

    def _outbox_from_record(self, record: OutboxMessageRecord) -> OutboxMessage:
        return OutboxMessage(
            id=record.id,
            event_id=record.event_id,
            channel=record.channel,
            payload=record.payload,
            status=record.status,
            attempts=record.attempts,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _optional_str(self, value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    def _optional_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value)
