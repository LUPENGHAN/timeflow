"""Reminder trigger interfaces and P0 active trigger checks."""

from __future__ import annotations

from datetime import datetime

from timeapp.domain.enums import ReminderTriggerType
from timeapp.domain.models import Reminder


class TimeTrigger:
    """Active P0 trigger for due-at reminders."""

    def is_due(self, reminder: Reminder, now: datetime) -> bool:
        """判断提醒是否到期。"""

        return (
            reminder.trigger_type == ReminderTriggerType.TIME
            and reminder.trigger_at is not None
            and reminder.trigger_at <= now
        )


class EnterPlaceTrigger:
    """Active P0 boundary for entering a place."""

    trigger_type = ReminderTriggerType.ENTER_PLACE


class LeavePlaceTrigger:
    """Active P0 boundary for leaving a place."""

    trigger_type = ReminderTriggerType.LEAVE_PLACE


class EnvironmentTrigger:
    """Skeleton trigger for future weather/noise/device-state combinations."""
