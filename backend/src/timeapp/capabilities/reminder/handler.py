"""Reminder capability handler and P0 reminder creation logic."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from timeapp.application.store import InMemoryStore
from timeapp.domain.enums import (
    DomainEventType,
    ReminderPriority,
    ReminderStatus,
    ReminderTriggerType,
)
from timeapp.domain.models import DomainEvent, Reminder, WriteRequest, utc_now


class ReminderCapability:
    """Create reminders only after their target item exists."""

    def apply(
        self,
        write_request: WriteRequest,
        store: InMemoryStore,
        item_id: str,
    ) -> list[DomainEvent]:
        """Create reminders from the confirmed candidate payload."""

        events: list[DomainEvent] = []
        reminder_payloads = write_request.candidate_payload.get("reminders", [])
        if not isinstance(reminder_payloads, list):
            return events

        for payload in reminder_payloads:
            if not isinstance(payload, dict):
                continue
            trigger_type = ReminderTriggerType(str(payload.get("trigger_type", "time")))
            reminder = Reminder(
                id=str(uuid4()),
                user_id=write_request.identity.user_id,
                item_id=item_id,
                trigger_type=trigger_type,
                trigger_at=self._optional_datetime(payload.get("trigger_at")),
                place_id=self._optional_str(payload.get("place_ref")),
                priority=ReminderPriority(
                    str(write_request.candidate_payload["item"].get("priority", "normal"))
                ),
                status=ReminderStatus.PENDING
                if trigger_type == ReminderTriggerType.TIME
                else ReminderStatus.ARMED,
            )
            store.add_reminder(reminder)
            event_type = (
                DomainEventType.WRITE_REQUEST_UPDATED
                if trigger_type == ReminderTriggerType.TIME
                else DomainEventType.REMINDER_ARMED
            )
            events.append(
                DomainEvent(
                    id=str(uuid4()),
                    event_type=event_type,
                    aggregate_type="reminder",
                    aggregate_id=reminder.id,
                    version=len(store.events) + len(events) + 1,
                    occurred_at=utc_now(),
                    payload={"reminder": self._reminder_payload(reminder)},
                )
            )
        return events

    def _optional_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value)

    def _optional_str(self, value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

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
        }
