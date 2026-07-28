"""Reminder capability: reminders and repeat rules.

Repeat rules only exist to support reminder triggers today, so their CRUD and
validation live here rather than in a standalone capability. Place data
(latitude/longitude/radius/place_type) lives directly on the `Item` a
reminder is bound to -- there is no separate Place entity.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from timeapp.application.store import Store
from timeapp.capabilities import item_common
from timeapp.context.policies import CloudFallbackPolicy, CooldownPolicy
from timeapp.domain.enums import (
    DomainEventType,
    FallbackStatus,
    NotificationRegistrationStatus,
    ReminderPriority,
    ReminderStatus,
    ReminderTriggerType,
)
from timeapp.domain.errors import ApplicationError, ErrorCode
from timeapp.domain.models import (
    DomainEvent,
    Identity,
    Reminder,
    RepeatRule,
    WriteRequest,
    utc_now,
)

REPEAT_PATTERNS = {"daily", "weekdays", "custom_weekdays"}
REPEAT_SERIES_STATUSES = {"active", "paused", "stopped"}
REPEAT_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
WORKWEEK_DAYS = [1, 2, 3, 4, 5]


class ReminderCapability:
    """Own reminder, place and repeat-rule creation, actions and validation."""

    def __init__(self) -> None:
        """初始化实例。"""
        self.cloud_fallback = CloudFallbackPolicy()
        self.cooldown = CooldownPolicy()

    # -- Reminder creation ----------------------------------------------------

    def create(
        self,
        store: Store,
        identity: Identity,
        item_id: str,
        trigger_type: ReminderTriggerType,
        trigger_at: datetime | None = None,
        priority: ReminderPriority = ReminderPriority.NORMAL,
    ) -> tuple[Reminder, list[DomainEvent]]:
        """创建提醒并返回产出的事件；调用方负责持久化事件（不在这里自己 add_events）。

        `apply_from_write_request` 在 write-request 确认流程里调用这个方法，
        confirm_write_request 会在最后统一 add_events 一次；如果这里自己再
        add_events，同一个事件对象会被插入两次，触发主键冲突。
        """

        item = store.get_item(item_id)
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
        if trigger_type != ReminderTriggerType.TIME and not item.place_text:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Place reminders require the target item to have place_text set.",
            )

        now = utc_now()
        initial_status = (
            ReminderStatus.ARMED
            if trigger_type in {ReminderTriggerType.ENTER_PLACE, ReminderTriggerType.LEAVE_PLACE}
            else ReminderStatus.PENDING
        )
        event_type = (
            DomainEventType.REMINDER_ARMED
            if initial_status == ReminderStatus.ARMED
            else DomainEventType.WRITE_REQUEST_UPDATED
        )
        reminder = Reminder(
            id=str(uuid4()),
            user_id=identity.user_id,
            item_id=item.id,
            trigger_type=trigger_type,
            trigger_at=trigger_at,
            priority=priority,
            status=initial_status,
            created_at=now,
            updated_at=now,
        )
        store.add_reminder(reminder)
        event = self._event(
            store,
            event_type,
            "reminder",
            reminder.id,
            {"reminder": self._reminder_payload(reminder)},
        )
        return reminder, [event]

    def apply_from_write_request(
        self,
        write_request: WriteRequest,
        store: Store,
        item_id_override: str | None = None,
    ) -> list[DomainEvent]:
        """应用from 写入 请求。"""

        target_id = item_id_override or item_common.optional_str(
            write_request.candidate_payload.get("target_id")
        )
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
            priority = ReminderPriority(
                str(
                    payload.get("priority")
                    or write_request.candidate_payload.get("item", {}).get("priority", "normal")
                )
            )
            _, reminder_events = self.create(
                store,
                identity=write_request.identity,
                item_id=target_id,
                trigger_type=trigger_type,
                trigger_at=item_common.optional_datetime(payload.get("trigger_at")),
                priority=priority,
            )
            events.extend(reminder_events)

        return events

    # -- Reminder actions -------------------------------------------------------

    def apply_action(
        self,
        store: Store,
        identity: Identity,
        reminder_id: str,
        action: str,
        failed_reason: str | None = None,
        local_notification_id: str | None = None,
        snooze_minutes: int = 10,
        fallback_after_seconds: int = 300,
    ) -> tuple[Reminder, list[DomainEvent]]:
        """应用action。"""

        reminder = store.get_reminder(reminder_id)
        if reminder is None or reminder.user_id != identity.user_id:
            raise ApplicationError(
                ErrorCode.REMINDER_NOT_FOUND,
                f"Reminder {reminder_id} was not found.",
            )

        now = utc_now()
        event_type = DomainEventType.WRITE_REQUEST_UPDATED
        fallback_payload: dict[str, object] = {}

        if action == "registered":
            reminder.local_registration_status = NotificationRegistrationStatus.REGISTERED
            reminder.local_notification_id = local_notification_id
        elif action == "armed":
            reminder.status = ReminderStatus.ARMED
            event_type = DomainEventType.REMINDER_ARMED
        elif action == "delivered":
            reminder.status = ReminderStatus.DELIVERED
            reminder.last_triggered_at = now
            event_type = DomainEventType.REMINDER_DELIVERED
        elif action == "dismiss":
            reminder.status = ReminderStatus.DISMISSED
            event_type = DomainEventType.REMINDER_DISMISSED
        elif action == "snooze":
            if not self.cooldown.can_snooze(reminder):
                raise ApplicationError(
                    ErrorCode.SNOOZE_LIMIT_REACHED,
                    f"Reminder {reminder_id} has already used its P0 snooze allowance.",
                )
            reminder.status = ReminderStatus.SNOOZED
            reminder.snooze_count += 1
            reminder.trigger_at = now + timedelta(minutes=snooze_minutes)
            event_type = DomainEventType.REMINDER_SNOOZED
        elif action == "cancel":
            reminder.status = ReminderStatus.CANCELLED
            reminder.cancelled_at = now
            event_type = DomainEventType.REMINDER_CANCELLED
        elif self.cloud_fallback.should_request(action):
            reminder.status = ReminderStatus.FAILED
            reminder.failed_reason = failed_reason or action
            reminder.local_registration_status = (
                NotificationRegistrationStatus.UNAVAILABLE
                if action == "local_unavailable"
                else NotificationRegistrationStatus.FAILED
            )
            fallback_payload = self.cloud_fallback.request(
                reminder=reminder,
                now=now,
                fallback_after_seconds=fallback_after_seconds,
                failed_reason=reminder.failed_reason,
            )
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
        store.update_reminder(reminder)
        events = [
            self._event(
                store,
                event_type,
                "reminder",
                reminder.id,
                {"reminder": self._reminder_payload(reminder)},
            )
        ]
        if reminder.fallback_status == FallbackStatus.REQUESTED:
            events.append(
                self._event(
                    store,
                    DomainEventType.NOTIFICATION_FALLBACK_REQUESTED,
                    "reminder",
                    reminder.id,
                    fallback_payload,
                )
            )
        store.add_events(events)
        return reminder, events

    # -- Repeat rule CRUD -------------------------------------------------------

    def create_repeat_rule(
        self,
        store: Store,
        identity: Identity,
        pattern: str,
        weekdays: list[int] | None = None,
        time_of_day: str | None = None,
        series_status: str = "active",
    ) -> RepeatRule:
        """创建重复规则。"""

        normalized_pattern = self._normalize_repeat_pattern(pattern)
        normalized_weekdays = self._normalize_repeat_weekdays(normalized_pattern, weekdays)
        normalized_time_of_day = self._normalize_repeat_time_of_day(time_of_day)
        normalized_series_status = self._normalize_repeat_series_status(series_status)

        now = utc_now()
        repeat_rule = RepeatRule(
            id=str(uuid4()),
            user_id=identity.user_id,
            pattern=normalized_pattern,
            weekdays=normalized_weekdays,
            time_of_day=normalized_time_of_day,
            series_status=normalized_series_status,
            created_at=now,
            updated_at=now,
        )
        store.add_repeat_rule(repeat_rule)
        return repeat_rule

    def _normalize_repeat_pattern(self, pattern: str) -> str:
        """处理提醒能力相关逻辑。"""
        normalized = pattern.strip()
        if normalized not in REPEAT_PATTERNS:
            raise ApplicationError(
                ErrorCode.INVALID_FIELD_VALUE,
                "Repeat pattern must be daily, weekdays, or custom_weekdays.",
            )
        return normalized

    def _normalize_repeat_weekdays(self, pattern: str, weekdays: list[int] | None) -> list[int]:
        """处理提醒能力相关逻辑。"""
        if pattern == "daily":
            return []
        if pattern == "weekdays":
            return list(WORKWEEK_DAYS)

        normalized = sorted(set(weekdays or []))
        if not normalized:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Custom weekday repeat rules require at least one weekday.",
            )
        if any(weekday < 1 or weekday > 7 for weekday in normalized):
            raise ApplicationError(
                ErrorCode.INVALID_FIELD_VALUE,
                "Repeat weekdays must be between 1 and 7.",
            )
        return normalized

    def _normalize_repeat_time_of_day(self, time_of_day: str | None) -> str:
        """处理提醒能力相关逻辑。"""
        if time_of_day is None or not time_of_day.strip():
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Repeat rules require time_of_day.",
            )
        normalized = time_of_day.strip()
        if not REPEAT_TIME_RE.fullmatch(normalized):
            raise ApplicationError(
                ErrorCode.INVALID_FIELD_VALUE,
                "Repeat time must use HH:MM in 24-hour time.",
            )
        return normalized

    def _normalize_repeat_series_status(self, series_status: str) -> str:
        """处理提醒能力相关逻辑。"""
        normalized = series_status.strip()
        if normalized not in REPEAT_SERIES_STATUSES:
            raise ApplicationError(
                ErrorCode.INVALID_FIELD_VALUE,
                "Repeat series status must be active, paused, or stopped.",
            )
        return normalized

    # -- Helpers ------------------------------------------------------------

    def _event(
        self,
        store: Store,
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
            version=len(store.events) + 1,
            occurred_at=utc_now(),
            payload=payload,
        )

    def _reminder_payload(self, reminder: Reminder) -> dict[str, Any]:
        """处理提醒能力相关逻辑。"""
        return {
            "id": reminder.id,
            "item_id": reminder.item_id,
            "trigger_type": reminder.trigger_type.value,
            "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
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
