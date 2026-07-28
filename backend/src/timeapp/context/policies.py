"""Delivery and cooldown policy boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta

from timeapp.domain.enums import FallbackStatus
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
    """Minimal P0 fallback policy for recording cloud handoff requests."""

    def should_request(self, action: str) -> bool:
        """Return whether a reminder action should queue fallback."""

        return action in {"failed", "registration_failed", "local_unavailable"}

    def request(
        self,
        reminder: Reminder,
        now: datetime,
        fallback_after_seconds: int,
        failed_reason: str | None,
    ) -> dict[str, object]:
        """Mark fallback as requested and return the payload to broadcast."""

        reminder.fallback_status = FallbackStatus.REQUESTED
        reminder.fallback_after_seconds = fallback_after_seconds
        reminder.fallback_requested_at = now
        return {
            "reminder_id": reminder.id,
            "fallback_after_seconds": fallback_after_seconds,
            "failed_reason": failed_reason,
        }


class QuietPeriodPolicy:
    """Skeleton policy for future user preference handling."""
