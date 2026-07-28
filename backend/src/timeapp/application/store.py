"""Storage implementations for the MS1 executable skeleton.

The in-memory store is kept for fast unit tests. The SQLAlchemy-backed store is
used by the API runtime so Swagger calls persist to the configured database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from timeapp.domain.enums import (
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
    DomainEvent,
    Item,
    Reminder,
    RepeatRule,
    WriteRequest,
)
from timeapp.infrastructure.models import (
    DomainEventRecord,
    ItemRecord,
    ReminderRecord,
    ReminderRuleRecord,
)


class Store(Protocol):
    """Structural interface shared by `InMemoryStore` and `SqlAlchemyStore`.

    Capability and application code should type their `store` parameter as
    this Protocol rather than `InMemoryStore | SqlAlchemyStore`. That makes
    mypy verify both concrete stores stay in sync on every method they share,
    instead of relying on the two implementations happening to agree.
    """

    @property
    def events(self) -> list[DomainEvent]:
        """获取事件列表。"""
        ...

    @property
    def write_requests(self) -> dict[str, WriteRequest]:
        """获取写请求映射。"""
        ...

    def add_write_request(self, write_request: WriteRequest) -> None:
        """新增写请求。"""
        ...

    def update_write_request(self, write_request: WriteRequest) -> None:
        """更新写请求。"""
        ...

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """按 ID 获取写请求。"""
        ...

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """列出当前用户待确认的写请求。"""
        ...

    def add_item(self, item: Item) -> None:
        """新增事项。"""
        ...

    def get_item(self, item_id: str) -> Item | None:
        """获取事项。"""
        ...

    def update_item(self, item: Item) -> None:
        """更新事项。"""
        ...

    def list_items(self, user_id: str) -> list[Item]:
        """列出用户事项。"""
        ...

    def add_repeat_rule(self, repeat_rule: RepeatRule) -> None:
        """新增重复规则。"""
        ...

    def list_repeat_rules(self, user_id: str) -> list[RepeatRule]:
        """列出用户重复规则。"""
        ...

    def add_reminder(self, reminder: Reminder) -> None:
        """新增提醒。"""
        ...

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """获取提醒。"""
        ...

    def update_reminder(self, reminder: Reminder) -> None:
        """更新提醒。"""
        ...

    def list_reminders(self, user_id: str) -> list[Reminder]:
        """列出用户提醒。"""
        ...

    def add_events(self, events: list[DomainEvent]) -> None:
        """新增事件。"""
        ...

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """列出指定游标之后的事件。"""
        ...


@dataclass(slots=True)
class WriteRequestMemoryStore:
    """Process-lifetime in-memory write-request bucket, shared across requests.

    `SqlAlchemyStore` is constructed fresh per HTTP request (see
    `api/dependencies.py`), so write requests can't live as a field on the
    store instance itself -- they would vanish before the client's follow-up
    confirm/reject request arrives. Callers share one instance across
    requests instead, the same pattern `RealtimeConnectionManager`
    (`api/realtime.py`) uses for WS connections.
    """

    _write_requests: dict[str, WriteRequest] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def add(self, write_request: WriteRequest) -> None:
        """新增写请求。"""

        with self._lock:
            self._write_requests[write_request.id] = write_request

    def update(self, write_request: WriteRequest) -> None:
        """更新写请求。"""

        self.add(write_request)

    def get(self, write_request_id: str) -> WriteRequest | None:
        """按 ID 获取写请求。"""

        with self._lock:
            return self._write_requests.get(write_request_id)

    def list_pending(self, user_id: str) -> list[WriteRequest]:
        """列出当前用户待确认的写请求。"""

        with self._lock:
            return [
                request
                for request in self._write_requests.values()
                if request.identity.user_id == user_id
                and request.status == WriteRequestStatus.PENDING
            ]

    @property
    def all(self) -> dict[str, WriteRequest]:
        """返回全部写请求的快照。"""

        with self._lock:
            return dict(self._write_requests)


@dataclass(slots=True)
class InMemoryStore:
    """Small explicit storage boundary used by tests and local skeleton routes."""

    write_requests: dict[str, WriteRequest] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    repeat_rules: dict[str, RepeatRule] = field(default_factory=dict)
    reminders: dict[str, Reminder] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock)

    def add_write_request(self, write_request: WriteRequest) -> None:
        """新增写请求。"""

        with self._lock:
            self.write_requests[write_request.id] = write_request

    def update_write_request(self, write_request: WriteRequest) -> None:
        """更新写请求。"""

        self.add_write_request(write_request)

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """按 ID 获取写请求。"""

        with self._lock:
            return self.write_requests.get(write_request_id)

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """列出当前用户待确认的写请求。"""

        with self._lock:
            return [
                request
                for request in self.write_requests.values()
                if request.identity.user_id == user_id
                and request.status == WriteRequestStatus.PENDING
            ]

    def add_item(self, item: Item) -> None:
        """新增事项。"""

        with self._lock:
            self.items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        """获取事项。"""

        with self._lock:
            return self.items.get(item_id)

    def update_item(self, item: Item) -> None:
        """更新事项。"""

        with self._lock:
            self.items[item.id] = item

    def add_repeat_rule(self, repeat_rule: RepeatRule) -> None:
        """新增重复规则。"""

        with self._lock:
            self.repeat_rules[repeat_rule.id] = repeat_rule

    def list_repeat_rules(self, user_id: str) -> list[RepeatRule]:
        """列出用户重复规则。"""

        with self._lock:
            return [
                repeat_rule
                for repeat_rule in self.repeat_rules.values()
                if repeat_rule.user_id == user_id
            ]

    def add_reminder(self, reminder: Reminder) -> None:
        """新增提醒。"""

        with self._lock:
            self.reminders[reminder.id] = reminder

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """获取提醒。"""

        with self._lock:
            return self.reminders.get(reminder_id)

    def update_reminder(self, reminder: Reminder) -> None:
        """更新提醒。"""

        with self._lock:
            self.reminders[reminder.id] = reminder

    def list_reminders(self, user_id: str) -> list[Reminder]:
        """列出用户提醒。"""

        with self._lock:
            return [reminder for reminder in self.reminders.values() if reminder.user_id == user_id]

    def add_events(self, events: list[DomainEvent]) -> None:
        """新增事件。"""

        with self._lock:
            start_version = len(self.events) + 1
            for index, event in enumerate(events):
                event.version = start_version + index
            self.events.extend(events)

    def list_items(self, user_id: str) -> list[Item]:
        """列出用户事项。"""

        with self._lock:
            return [
                item
                for item in self.items.values()
                if item.user_id == user_id and item.status != ItemStatus.DELETED
            ]

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """列出事件 after。"""

        with self._lock:
            return self.events[cursor:]


class SqlAlchemyStore:
    """SQLAlchemy implementation used by the real API runtime.

    `write_requests` is intentionally NOT persisted to the database -- see
    `WriteRequestMemoryStore`'s docstring. Callers must pass a shared
    instance so pending write requests survive across the per-request
    `SqlAlchemyStore` objects FastAPI constructs.
    """

    def __init__(self, session: Session, write_requests: WriteRequestMemoryStore) -> None:
        """初始化实例。"""
        self.session = session
        self._write_requests = write_requests

    @property
    def events(self) -> list[DomainEvent]:
        """处理SQLAlchemy 存储相关逻辑。"""

        return self.list_events_after(0)

    @property
    def write_requests(self) -> dict[str, WriteRequest]:
        """处理SQLAlchemy 存储相关逻辑。"""

        return self._write_requests.all

    @property
    def reminders(self) -> dict[str, Reminder]:
        """处理SQLAlchemy 存储相关逻辑。"""

        records = self.session.scalars(select(ReminderRecord)).all()
        return {record.id: self._reminder_from_record(record) for record in records}

    def add_write_request(self, write_request: WriteRequest) -> None:
        """新增写请求。"""

        self._write_requests.add(write_request)

    def update_write_request(self, write_request: WriteRequest) -> None:
        """更新写请求。"""

        self._write_requests.update(write_request)

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """按 ID 获取写请求。"""

        return self._write_requests.get(write_request_id)

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """列出当前用户待确认的写请求。"""

        return self._write_requests.list_pending(user_id)

    def add_item(self, item: Item) -> None:
        """新增事项。"""

        self.session.add(self._item_to_record(item))
        self.session.flush()

    def get_item(self, item_id: str) -> Item | None:
        """获取事项。"""

        record = self.session.get(ItemRecord, item_id)
        return self._item_from_record(record) if record is not None else None

    def update_item(self, item: Item) -> None:
        """更新事项。"""

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
        record.place_type = item.place_type
        record.latitude = item.latitude
        record.longitude = item.longitude
        record.accuracy_meters = item.accuracy_meters
        record.radius_meters = item.radius_meters
        record.timezone = item.timezone
        record.version = item.version
        record.updated_at = item.updated_at
        record.deleted_at = item.updated_at if item.status == ItemStatus.DELETED else None
        self.session.flush()

    def list_items(self, user_id: str) -> list[Item]:
        """列出用户事项。"""

        records = self.session.scalars(
            select(ItemRecord)
            .where(
                ItemRecord.user_id == user_id,
                ItemRecord.status != ItemStatus.DELETED.value,
            )
            .order_by(ItemRecord.created_at)
        ).all()
        return [self._item_from_record(record) for record in records]

    def add_repeat_rule(self, repeat_rule: RepeatRule) -> None:
        """新增重复规则。"""

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
        self.session.flush()

    def list_repeat_rules(self, user_id: str) -> list[RepeatRule]:
        """列出用户重复规则。"""

        records = self.session.scalars(
            select(ReminderRuleRecord)
            .where(ReminderRuleRecord.user_id == user_id)
            .order_by(ReminderRuleRecord.created_at)
        ).all()
        return [self._repeat_rule_from_record(record) for record in records]

    def add_reminder(self, reminder: Reminder) -> None:
        """新增提醒。"""

        self.session.add(self._reminder_to_record(reminder))
        self.session.flush()

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        """获取提醒。"""

        record = self.session.get(ReminderRecord, reminder_id)
        return self._reminder_from_record(record) if record is not None else None

    def update_reminder(self, reminder: Reminder) -> None:
        """更新提醒。"""

        record = self.session.get(ReminderRecord, reminder.id)
        if record is None:
            self.add_reminder(reminder)
            return
        record.trigger_type = reminder.trigger_type.value
        record.trigger_at = reminder.trigger_at
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
        self.session.flush()

    def list_reminders(self, user_id: str) -> list[Reminder]:
        """列出用户提醒。"""

        records = self.session.scalars(
            select(ReminderRecord)
            .where(ReminderRecord.user_id == user_id)
            .order_by(ReminderRecord.created_at)
        ).all()
        return [self._reminder_from_record(record) for record in records]

    def add_events(self, events: list[DomainEvent]) -> None:
        """新增事件。"""

        current_max_version = self.session.scalar(
            select(DomainEventRecord.version).order_by(DomainEventRecord.version.desc()).limit(1)
        )
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
            start_version += 1
        self.session.flush()

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """列出事件 after。"""

        records = self.session.scalars(
            select(DomainEventRecord)
            .where(DomainEventRecord.version > cursor)
            .order_by(DomainEventRecord.version)
        ).all()
        return [self._event_from_record(record) for record in records]

    def _item_to_record(self, item: Item) -> ItemRecord:
        """将事项转换为记录。"""
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
            place_type=item.place_type,
            latitude=item.latitude,
            longitude=item.longitude,
            accuracy_meters=item.accuracy_meters,
            radius_meters=item.radius_meters,
            timezone=item.timezone,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.updated_at if item.status == ItemStatus.DELETED else None,
        )

    def _item_from_record(self, record: ItemRecord) -> Item:
        """从记录还原事项。"""
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
            place_type=record.place_type,
            latitude=record.latitude,
            longitude=record.longitude,
            accuracy_meters=record.accuracy_meters,
            radius_meters=record.radius_meters,
            timezone=record.timezone,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _repeat_rule_from_record(self, record: ReminderRuleRecord) -> RepeatRule:
        """从记录还原重复规则。"""
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
        """将提醒转换为记录。"""
        return ReminderRecord(
            id=reminder.id,
            user_id=reminder.user_id,
            item_id=reminder.item_id,
            trigger_type=reminder.trigger_type.value,
            trigger_at=reminder.trigger_at,
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
        """从记录还原提醒。"""
        return Reminder(
            id=record.id,
            user_id=record.user_id,
            item_id=record.item_id,
            trigger_type=ReminderTriggerType(record.trigger_type),
            trigger_at=record.trigger_at,
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
        """从记录还原事件。"""
        return DomainEvent(
            id=record.id,
            event_type=DomainEventType(record.event_type),
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            version=record.version,
            occurred_at=record.occurred_at,
            payload=record.payload,
        )

    def _optional_str(self, value: object) -> str | None:
        """处理SQLAlchemy 存储相关逻辑。"""
        return value if isinstance(value, str) and value else None
