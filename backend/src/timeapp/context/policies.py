"""Delivery and cooldown policy boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta

from timeapp.domain.models import Reminder


class LocalNotificationPolicy:
    """Active P0 policy for local notification handoff."""

    channel = "local_notification"

    def notification_payload(self, reminder: Reminder) -> dict[str, str]:
        """Return a minimal notification payload."""

        return {"reminder_id": reminder.id, "item_id": reminder.item_id}


class CooldownPolicy:
    """Minimal P0 duplicate guard and one-time snooze boundary."""

    def can_trigger(self, reminder: Reminder, now: datetime) -> bool:
        """Return false when the reminder just triggered recently."""

        if reminder.last_triggered_at is None:
            return True
        return reminder.last_triggered_at + timedelta(minutes=1) <= now

    def can_snooze(self, reminder: Reminder) -> bool:
        """P0 allows one simple snooze."""

        return reminder.snooze_count == 0


class VibrationPolicy:
    """Skeleton policy for P1 stronger local delivery."""


class VoicePolicy:
    """Skeleton policy for P1 voice playback."""


class CloudFallbackPolicy:
    """Skeleton policy for P2 cloud delivery channels."""


class QuietPeriodPolicy:
    """Skeleton policy for future user preference handling."""
