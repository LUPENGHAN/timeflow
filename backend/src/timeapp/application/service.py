"""P0 application service: command intake, confirmation gate and event output."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from timeapp.ai.parser import LLMCommandParser, MockCommandParser
from timeapp.application.reference_resolver import ReferenceResolver
from timeapp.application.store import InMemoryStore, Store
from timeapp.capabilities import item_common
from timeapp.capabilities.calendar.handler import CalendarCapability
from timeapp.capabilities.reminder.handler import ReminderCapability
from timeapp.capabilities.todo.handler import TodoCapability
from timeapp.domain.enums import (
    CommandAction,
    CommandEntity,
    DomainEventType,
    ItemStatus,
    ItemType,
    ReminderPriority,
    ReminderTriggerType,
    VoiceCommandStatus,
    WriteRequestStatus,
)
from timeapp.domain.errors import ApplicationError as ApplicationError
from timeapp.domain.errors import ErrorCode
from timeapp.domain.models import (
    Command,
    DomainEvent,
    Identity,
    Item,
    Reminder,
    RepeatRule,
    VoiceCommand,
    WriteRequest,
)


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

    def __init__(
        self,
        store: Store | None = None,
        parser: MockCommandParser | LLMCommandParser | None = None,
    ) -> None:
        """初始化实例。"""
        self.store = store or InMemoryStore()
        self.parser = parser or MockCommandParser()
        self.reference_resolver = ReferenceResolver()
        self.calendar = CalendarCapability()
        self.todo = TodoCapability()
        self.reminder = ReminderCapability()

    def submit_voice_command(self, transcript: str, identity: Identity) -> VoiceCommandResult:
        """提交语音命令，解析后生成写请求或候选项。"""

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

        match_candidates: list[Item] = []
        if command.action in {CommandAction.UPDATE, CommandAction.DELETE, CommandAction.COMPLETE}:
            match_candidates = self.reference_resolver.resolve_item_candidates(command, self.store)
            if not match_candidates:
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

            if len(match_candidates) > 1:
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
                candidate_payload = self._candidate_payload(command, match_candidates)
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
                    candidates=match_candidates,
                )

        candidate_payload = self._candidate_payload(command, match_candidates)
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
        """列出当前用户待确认的写请求。"""

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
        """按 ID 获取写请求。"""

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
        """确认写请求并应用变更。"""

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
        # item_common.update_item_fields() already persists its own event for these
        # four operations, so `events` here is already in the DB -- only add the new
        # applied_event, or it would insert the same event id twice. Every other
        # operation (including create_reminder/create_todo_with_reminder) routes
        # through capability `apply()`/`create()` methods that return events without
        # persisting them, so this is the only place they get added.
        operation = str(write_request.candidate_payload.get("operation", ""))
        if operation in {
            "update_item",
            "complete_item",
            "cancel_complete_item",
            "delete_item",
        }:
            self.store.add_events([applied_event])
        else:
            self.store.add_events([*events, applied_event])
        return ConfirmationResult(write_request, [*events, applied_event])

    def reject_write_request(self, write_request_id: str, identity: Identity) -> ConfirmationResult:
        """拒绝写请求。"""

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
        """更新写请求。"""

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
        """列出用户事项。"""

        return self.store.list_items(identity.user_id)

    def _query_items(self, command: Command) -> list[Item]:
        """查询事项候选列表。"""

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
        """生成事项排序键。"""
        anchor = item.start_at or item.due_at
        if anchor is None:
            return (1, item.updated_at, item.title)
        return (0, anchor, item.title)

    def list_repeat_rules(self, identity: Identity) -> list[RepeatRule]:
        """列出用户重复规则。"""

        return self.store.list_repeat_rules(identity.user_id)

    def list_reminders(self, identity: Identity) -> list[Reminder]:
        """列出用户提醒。"""

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
        place_type: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        accuracy_meters: int | None = None,
        radius_meters: int = 100,
    ) -> tuple[Item, list[DomainEvent]]:
        """创建事项。"""

        return item_common.create_item(
            self.store,
            identity=identity,
            item_type=item_type,
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            due_at=due_at,
            place_text=place_text,
            place_type=place_type,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy_meters,
            radius_meters=radius_meters,
        )

    def create_repeat_rule(
        self,
        identity: Identity,
        pattern: str,
        weekdays: list[int] | None = None,
        time_of_day: str | None = None,
        series_status: str = "active",
    ) -> RepeatRule:
        """创建重复规则。"""

        return self.reminder.create_repeat_rule(
            self.store,
            identity=identity,
            pattern=pattern,
            weekdays=weekdays,
            time_of_day=time_of_day,
            series_status=series_status,
        )

    def create_reminder(
        self,
        identity: Identity,
        item_id: str,
        trigger_type: ReminderTriggerType,
        trigger_at: datetime | None = None,
        priority: ReminderPriority = ReminderPriority.NORMAL,
    ) -> tuple[Reminder, list[DomainEvent]]:
        """创建提醒（直接 API 路径，不经过 write-request 确认流程，需要自己持久化事件）。"""

        reminder, events = self.reminder.create(
            self.store,
            identity=identity,
            item_id=item_id,
            trigger_type=trigger_type,
            trigger_at=trigger_at,
            priority=priority,
        )
        self.store.add_events(events)
        return reminder, events

    def degrade_permission(
        self,
        identity: Identity,
        permission: str,
        reason: str,
        title: str,
        place_text: str | None = None,
    ) -> tuple[Item, list[DomainEvent]]:
        """处理权限降级。"""

        return item_common.degrade_permission(
            self.store,
            identity=identity,
            permission=permission,
            reason=reason,
            title=title,
            place_text=place_text,
        )

    def create_write_request(
        self,
        identity: Identity,
        source_command_id: str,
        candidate_payload: dict[str, Any],
    ) -> tuple[WriteRequest, list[DomainEvent]]:
        """创建写请求。"""

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
        place_type: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        accuracy_meters: int | None = None,
        radius_meters: int | None = None,
        status: ItemStatus | None = None,
    ) -> tuple[Item, list[DomainEvent]]:
        """更新事项。"""

        return item_common.update_item(
            self.store,
            identity=identity,
            item_id=item_id,
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            due_at=due_at,
            place_text=place_text,
            place_type=place_type,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy_meters,
            radius_meters=radius_meters,
            status=status,
        )

    def update_item_fields(
        self,
        identity: Identity,
        item_id: str,
        changes: dict[str, Any],
    ) -> tuple[Item, list[DomainEvent]]:
        """按指定字段更新事项。"""

        return item_common.update_item_fields(self.store, identity, item_id, changes)

    def delete_item(self, identity: Identity, item_id: str) -> tuple[Item, list[DomainEvent]]:
        """删除事项。"""

        return item_common.delete_item(self.store, identity, item_id)

    def complete_item(self, identity: Identity, item_id: str) -> tuple[Item, list[DomainEvent]]:
        """将事项标记为已完成。"""

        return item_common.complete_item(self.store, identity, item_id)

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
        """应用提醒动作。"""

        return self.reminder.apply_action(
            self.store,
            identity=identity,
            reminder_id=reminder_id,
            action=action,
            failed_reason=failed_reason,
            local_notification_id=local_notification_id,
            snooze_minutes=snooze_minutes,
            fallback_after_seconds=fallback_after_seconds,
        )

    def list_events(self, after_cursor: int = 0) -> list[DomainEvent]:
        """列出事件。"""

        return self.store.list_events_after(after_cursor)

    def _load_pending_request(self, write_request_id: str, identity: Identity) -> WriteRequest:
        """加载待处理写请求。"""
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
        """构建候选载荷。"""
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
                item_common.item_payload(candidate) for candidate in candidates or []
            ]
        if "reminder" in command.payload:
            reminder_payload = command.payload["reminder"]
            payload["reminders"] = [reminder_payload]
            place_ref = (
                reminder_payload.get("place_ref") if isinstance(reminder_payload, dict) else None
            )
            if place_ref and not payload["item"].get("place_text"):
                payload["item"]["place_text"] = place_ref
        return payload

    def _apply_write_request(self, write_request: WriteRequest) -> list[DomainEvent]:
        """应用写请求。"""
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
            events.extend(
                self.reminder.apply_from_write_request(
                    write_request, self.store, item_id_override=item_id
                )
            )
            return events

        if operation == "create_reminder":
            return self.reminder.apply_from_write_request(write_request, self.store)

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
        """应用事项操作。"""
        operations = write_request.candidate_payload.get("operations", [])
        if not isinstance(operations, list) or not operations:
            target_id = item_common.optional_str(write_request.candidate_payload.get("target_id"))
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
            target_id = item_common.optional_str(operation.get("target_id"))
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

    def _last_created_item_id(self, events: list[DomainEvent]) -> str:
        """提取最近创建的事项 ID。"""
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
        """构造领域事件。"""
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
        """计算载荷哈希。"""
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _command_from_candidate_payload(
        self,
        identity: Identity,
        source_command_id: str,
        candidate_payload: dict[str, Any],
    ) -> Command:
        """从候选载荷还原命令。"""
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
            description=item_common.optional_str(item_payload.get("description")),
            target_id=item_common.optional_str(candidate_payload.get("target_id")),
            start_at=item_common.optional_datetime(item_payload.get("start_at")),
            end_at=item_common.optional_datetime(item_payload.get("end_at")),
            due_at=item_common.optional_datetime(item_payload.get("due_at")),
            payload=candidate_payload,
        )

